"""CSV import: parse, map, normalize, dedup, suppress. Runs in the worker in atomic chunks so a
crash re-runs the chunk without duplicating leads (unique(batch,row) + resume cursor)."""
import csv
import hashlib
import io
import re
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain import normalize as n
from app.domain.dedup import Identity
from app.jobs import queue
from app.models import Company, ImportBatch, ImportRowError, Job, Lead
from app.repos.leads import LeadRepo
from app.repos.suppression import SuppressionRepo
from app.services.audit import activity, audit

TARGET_FIELDS = [
    "company_name", "first_name", "last_name", "title", "email", "phone", "website",
    "linkedin_url", "instagram_url", "location", "industry", "description", "source_url", "region",
]
_HINTS: dict[str, list[str]] = {
    "company_name": ["company", "company name", "business", "business name", "organization", "organisation"],
    "first_name": ["first name", "firstname", "first", "given name"],
    "last_name": ["last name", "lastname", "last", "surname", "family name"],
    "title": ["title", "job title", "position", "role"],
    "email": ["email", "e-mail", "email address", "mail"],
    "phone": ["phone", "phone number", "mobile", "tel", "telephone", "contact number"],
    "website": ["website", "url", "web", "domain", "site", "company website"],
    "linkedin_url": ["linkedin", "linkedin url", "linkedin profile"],
    "instagram_url": ["instagram", "instagram url", "instagram profile", "ig"],
    "location": ["location", "address", "city", "company location"],
    "industry": ["industry", "category", "sector"],
    "description": ["description", "about", "bio", "company description"],
    "source_url": ["source", "source url", "source_url", "scraped from"],
    "region": ["country", "region", "country code"],
}


class ImportError_(ValueError):
    """User-facing import problem (bad file, bad mapping)."""


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used: set[str] = set()
    by_key = {_key(h): h for h in headers}
    for target, hints in _HINTS.items():
        for hint in hints:
            h = by_key.get(_key(hint))
            if h and h not in used:
                mapping[target] = h
                used.add(h)
                break
    return mapping


def parse_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    s = get_settings()
    if len(data) > s.max_upload_bytes:
        raise ImportError_(f"file exceeds {s.max_upload_bytes // (1024 * 1024)} MB limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportError_("file must be UTF-8 encoded") from exc
    if "\x00" in text:
        raise ImportError_("file looks binary, not CSV")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t") if text else csv.excel
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text, newline=""), dialect)
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise ImportError_("file is empty") from None
    headers = []
    for i, h in enumerate(raw_headers):
        h = h.strip() or f"column_{i + 1}"
        while h in headers:
            h += "_dup"
        headers.append(h)
    rows: list[dict[str, str]] = []
    for rec in reader:
        if not any(c.strip() for c in rec):
            continue  # skip blank lines
        if len(rows) >= s.max_import_rows:
            raise ImportError_(f"file exceeds {s.max_import_rows} row limit")
        rec = (rec + [""] * len(headers))[: len(headers)]
        rows.append(dict(zip(headers, rec, strict=True)))
    return headers, rows


def create_batch(db: Session, ws: uuid.UUID, user_id: uuid.UUID | None, filename: str,
                 data: bytes, default_region: str | None = None) -> ImportBatch:
    headers, rows = parse_csv(data)
    batch = ImportBatch(
        workspace_id=ws, created_by=user_id, filename=filename[:300],
        file_sha256=hashlib.sha256(data).hexdigest(), file_bytes=data, headers=headers,
        mapping=suggest_mapping(headers), total_rows=len(rows),
        default_region=default_region.upper() if default_region else None,
    )
    db.add(batch)
    db.flush()
    audit(db, ws, user_id, "import.upload", str(batch.id), filename=filename, rows=len(rows))
    return batch


def preview(batch: ImportBatch, limit: int = 20) -> list[dict[str, str]]:
    _, rows = parse_csv(batch.file_bytes)
    return rows[:limit]


def validate_mapping(headers: list[str], mapping: dict[str, str]) -> None:
    for target, col in mapping.items():
        if target not in TARGET_FIELDS:
            raise ImportError_(f"unknown target field {target!r}")
        if col not in headers:
            raise ImportError_(f"column {col!r} not in file")
    if len(set(mapping.values())) != len(mapping):
        raise ImportError_("a column can only be mapped once")
    if not any(k in mapping for k in ("email", "phone", "linkedin_url", "instagram_url", "website")):
        raise ImportError_("map at least one contact field (email, phone, website, LinkedIn or Instagram)")


# ---------- row processing ----------

def _country(v: str | None) -> str | None:
    v = n.blank(v)
    return v.upper() if v and re.fullmatch(r"[A-Za-z]{2}", v) else None


def process_row(db: Session, ws: uuid.UUID, batch: ImportBatch, row_no: int, raw: dict[str, str]) -> str:
    """Returns outcome: created | suppressed | duplicate | invalid. Writes lead or error row."""
    repo, sup = LeadRepo(db, ws), SuppressionRepo(db, ws)
    m = {t: n.blank(raw.get(c)) for t, c in batch.mapping.items()}
    mapped_cols = set(batch.mapping.values())
    custom: dict[str, Any] = {c: v.strip() for c, v in raw.items() if c not in mapped_cols and v and v.strip()}
    warnings: list[str] = []

    region = _country(m.get("region"))
    email_norm = n.normalize_email(m.get("email"))
    if m.get("email") and not email_norm:
        warnings.append("invalid email ignored")
    phone = n.normalize_phone(m.get("phone"), region or batch.default_region)
    if m.get("phone") and not phone:
        warnings.append("invalid phone ignored")
    linkedin = n.normalize_linkedin(m.get("linkedin_url"))
    if m.get("linkedin_url") and not linkedin:
        warnings.append("linkedin url is not a personal /in/ profile; ignored")
    instagram = n.normalize_instagram(m.get("instagram_url"))
    if m.get("instagram_url") and not instagram:
        warnings.append("invalid instagram url ignored")
    website = n.normalize_website(m.get("website"))
    if m.get("website") and not website:
        warnings.append("invalid website ignored")

    def fail(kind: str, reason: str, existing: uuid.UUID | None = None) -> str:
        db.add(_error_row(ws, batch.id, row_no, kind, reason, existing, raw))
        return kind

    if not (email_norm or phone or linkedin or instagram or website):
        return fail("invalid", "no valid contact field (" + "; ".join(warnings or ["all empty"]) + ")")

    ident = Identity(email_norm, phone, linkedin, instagram)
    dup = repo.find_duplicate(ident)
    if dup:
        return fail("duplicate", f"matches existing lead on {dup[1]}", dup[0].id)

    domain = n.domain_of_website(website) or n.domain_of_email(email_norm)
    company_id = None
    if domain or m.get("company_name"):
        company = repo.find_company_by_domain(domain) if domain else None
        if company is None:
            company = Company(workspace_id=ws, name=m.get("company_name"), domain=domain,
                              website=website, location=m.get("location"),
                              industry=m.get("industry"), description=m.get("description"))
            db.add(company)
            db.flush()
        company_id = company.id

    suggested = repo.same_domain_same_lastname(domain, m.get("last_name"))
    suppressed_reason = sup.is_suppressed(email_norm, phone)
    if warnings:
        custom["_import_warnings"] = warnings
    lead = Lead(
        workspace_id=ws, company_id=company_id, import_batch_id=batch.id, import_row=row_no,
        first_name=m.get("first_name"), last_name=m.get("last_name"), title=m.get("title"),
        email=m.get("email"), email_norm=email_norm, phone=m.get("phone"), phone_e164=phone,
        linkedin_url=linkedin, instagram_url=instagram, source_url=m.get("source_url"),
        collected_at=datetime.now(timezone.utc), region=region, custom=custom, raw=raw,
        status="suppressed" if suppressed_reason else "imported",
        opted_out=bool(suppressed_reason),
        possible_duplicate_of=suggested.id if suggested else None,
    )
    try:
        with db.begin_nested():
            db.add(lead)
            db.flush()
            activity(db, ws, lead.id, "lead.imported", batch_id=str(batch.id), row=row_no,
                     suppressed=suppressed_reason)
    except IntegrityError:
        return fail("duplicate", "concurrent duplicate on email")
    return "suppressed" if suppressed_reason else "created"


def _error_row(ws, batch_id, row_no, kind, reason, existing, raw) -> ImportRowError:
    return ImportRowError(workspace_id=ws, batch_id=batch_id, row_number=row_no, kind=kind,
                          reason=reason[:500], existing_lead_id=existing, raw=raw)


def refresh_counts(db: Session, batch: ImportBatch) -> None:
    """Counts are derived from records so they always match the data."""
    def errs(kind: str) -> int:
        return db.scalar(select(func.count()).select_from(ImportRowError).where(
            ImportRowError.batch_id == batch.id, ImportRowError.kind == kind)) or 0

    def leads(suppressed: bool) -> int:
        cond = Lead.status == "suppressed" if suppressed else Lead.status != "suppressed"
        return db.scalar(select(func.count()).select_from(Lead).where(
            Lead.import_batch_id == batch.id, cond)) or 0

    batch.invalid_count, batch.duplicate_count = errs("invalid"), errs("duplicate")
    batch.created_count, batch.suppressed_count = leads(False), leads(True)


def _iter_rows(batch: ImportBatch, start: int) -> Iterator[tuple[int, dict[str, str]]]:
    _, rows = parse_csv(batch.file_bytes)
    for i in range(start, len(rows) + 1):
        yield i, rows[i - 1]


def enqueue_import(db: Session, batch: ImportBatch, mode: str = "full") -> Job:
    validate_mapping(batch.headers, batch.mapping)
    batch.status = "queued"
    batch.error = None
    return queue.enqueue(db, "import_csv", {"batch_id": str(batch.id), "mode": mode}, batch.workspace_id)


@queue.handler("import_csv")
def run_import(db: Session, job: Job) -> None:
    batch = db.get(ImportBatch, uuid.UUID(job.payload["batch_id"]))
    if batch is None:
        raise RuntimeError("import batch not found")
    ws, size = batch.workspace_id, get_settings().import_chunk_size
    batch.status = "running"
    db.commit()

    if job.payload.get("mode") == "retry":
        _retry_invalid(db, batch)
    else:
        pending: list[tuple[int, dict[str, str]]] = []

        def flush_chunk() -> None:
            for row_no, raw in pending:
                process_row(db, ws, batch, row_no, raw)
            batch.next_row = pending[-1][0] + 1
            refresh_counts(db, batch)
            db.get(Job, job.id).lease_until = queue.now() + _lease()  # heartbeat
            db.commit()  # chunk + cursor commit atomically
            pending.clear()

        for item in _iter_rows(batch, batch.next_row):
            pending.append(item)
            if len(pending) >= size:
                flush_chunk()
        if pending:
            flush_chunk()

    refresh_counts(db, batch)
    batch.status = "completed"
    audit(db, ws, batch.created_by, "import.completed", str(batch.id),
          created=batch.created_count, duplicates=batch.duplicate_count,
          invalid=batch.invalid_count, suppressed=batch.suppressed_count)
    db.commit()


def _lease():
    from datetime import timedelta
    return timedelta(seconds=get_settings().job_lease_seconds)


def _retry_invalid(db: Session, batch: ImportBatch) -> None:
    """Re-process only failed 'invalid' rows; successful rows are never touched."""
    errors = list(db.scalars(select(ImportRowError).where(
        ImportRowError.batch_id == batch.id, ImportRowError.kind == "invalid")
        .order_by(ImportRowError.row_number)))
    for err in errors:
        raw = err.raw
        row_no = err.row_number
        db.delete(err)
        db.flush()
        process_row(db, batch.workspace_id, batch, row_no, raw)
    db.commit()
