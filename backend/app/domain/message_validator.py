"""Deterministic checks on generated messages. A draft is never trusted because a model produced it."""
import re
from dataclasses import dataclass, field

LIMITS = {"email": {"max_words": 130, "max_subject": 80}, "linkedin": {"max_chars": 300}, "instagram": {"max_chars": 300}}
BANNED = ["hope this email finds you well", "revolutionary", "game-changing", "game changing", "guaranteed",
          "100%", "act now", "limited time", "as an ai", "i noticed you're struggling", "i love your"]
_NUMERIC = re.compile(r"(\$\s?\d|\d+\s?%|\b\d{2,}\b\s+(?:clients|customers|companies|employees|patients))", re.I)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[\"'“”‘’]", "", s)).strip().lower()


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verified_claims: int = 0
    removed_claims: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"errors": self.errors, "warnings": self.warnings, "verified_claims": self.verified_claims,
                "removed_claims": self.removed_claims, "ok": self.ok}


def verify_claims(claims: list[dict], evidence: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Split claims into (verified, unsupported). Verified = cites a *verified* evidence item whose excerpt
    contains the quoted text. Inferred evidence can never support a factual statement."""
    good, bad = [], []
    for c in claims:
        ev = evidence.get(str(c.get("evidence_id")))
        quote = norm(c.get("quote") or "")
        if ev and ev.get("kind") == "verified" and quote and quote in norm(ev["excerpt"]):
            good.append(c)
        else:
            bad.append(c)
    return good, bad


def strip_unsupported(body: str, unsupported: list[dict]) -> tuple[str, list[str]]:
    removed = []
    for c in unsupported:
        text = (c.get("text") or "").strip()
        if text and text in body:
            body = body.replace(text, "").replace("  ", " ")
            removed.append(text)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body, removed


def validate(channel: str, subject: str | None, body: str, verified_claims: list[dict],
             removed: list[str] | None = None) -> Report:
    r = Report(verified_claims=len(verified_claims), removed_claims=removed or [])
    lim = LIMITS.get(channel, {})
    if not body.strip():
        r.errors.append("empty body")
    if re.search(r"\{\{|\}\}|\[[A-Z _]{3,}\]|<[a-z_]+>", body):
        r.errors.append("unresolved placeholder in text")
    low = body.lower()
    for b in BANNED:
        if b in low:
            r.errors.append(f"banned/spammy phrase: '{b}'")
    if channel == "email":
        if not subject or not subject.strip():
            r.errors.append("missing subject")
        elif len(subject) > lim["max_subject"]:
            r.errors.append(f"subject longer than {lim['max_subject']} chars")
        elif subject.isupper() or "!" in subject:
            r.warnings.append("subject looks promotional")
        if len(body.split()) > lim["max_words"]:
            r.errors.append(f"body longer than {lim['max_words']} words")
    elif "max_chars" in lim and len(body) > lim["max_chars"]:
        r.errors.append(f"body longer than {lim['max_chars']} characters for {channel}")
    verified_text = " ".join(c.get("text", "") for c in verified_claims)
    for m in _NUMERIC.finditer(body):
        if m.group(0) not in verified_text:
            r.errors.append(f"unverified figure '{m.group(0).strip()}' (not backed by evidence)")
    if r.removed_claims:
        r.warnings.append(f"{len(r.removed_claims)} unsupported claim(s) removed")
    if not verified_claims:
        r.warnings.append("no evidence-backed personalization; conservative fallback, manual review advised")
    return r
