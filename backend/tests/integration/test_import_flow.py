import time

from sqlalchemy import func, select

from app.models import Job, Lead
from tests.conftest import H, do_import, run_all_jobs, upload

CSV = '''Company,First Name,Last Name,Email,Phone,Website,LinkedIn,Country,Notes
"Acme, Inc.",Jane,Doe,jane@acme.com,+91 98765 43210,acme.com,https://linkedin.com/in/jane-doe,IN,"likes ""tools"""
Acme Inc,Jim,Doe,JANE@ACME.COM,,acme.com,,IN,duplicate email
Beta Ltd,Bob,Ray,bob@beta.io,,beta.io,,GB,
Bad Row,,,not-an-email,,,,,
Gamma,Gina,Lee,,+91 99999 00000,gamma.co,,IN,phone only
Zed,Zoe,Doe,zoe@acme.com,,,,,same domain same lastname
'''


def test_full_import(client, db):
    res = do_import(client, CSV)
    assert res["status"] == "completed"
    assert res["total_rows"] == 6
    assert res["created_count"] == 4 and res["duplicate_count"] == 1 and res["invalid_count"] == 1
    leads = client.get("/api/v1/leads").json()["items"]
    assert len(leads) == 4
    jane = next(l for l in leads if l["email_norm"] == "jane@acme.com")
    assert jane["phone_e164"] == "+919876543210" and jane["custom"]["Notes"] == 'likes "tools"'
    zoe = next(l for l in leads if l["email_norm"] == "zoe@acme.com")
    assert zoe["possible_duplicate_of"] == jane["id"]          # suggested, never auto-merged
    # the "Acme, Inc." rows share one company by domain; names are not used to merge
    assert db.scalar(select(func.count()).select_from(Lead).where(Lead.company_id == jane["company_id"])) == 2


def test_errors_csv_is_formula_safe(client):
    res = do_import(client, "Email,Company\n@bad,=1+1\n")
    body = client.get(f"/api/v1/imports/{res['id']}/errors.csv").text
    assert "'=1+1" in body and ",=1+1" not in body


def test_reimport_creates_no_duplicates(client, db):
    do_import(client, CSV)
    res = do_import(client, CSV)
    assert res["created_count"] == 0 and res["duplicate_count"] == 5
    assert db.scalar(select(func.count()).select_from(Lead)) == 4


def test_reimport_job_rerun_is_idempotent(client, db):
    """Crash simulation: running the same import job twice must not duplicate leads."""
    res = do_import(client, CSV)
    job = db.scalars(select(Job)).first()
    job.state, job.attempts = "pending", 0
    from app.models import ImportBatch
    b = db.get(ImportBatch, res["id"]); b.next_row = 1; b.status = "queued"
    db.commit()
    # leads exist already, rows 1..6 are re-processed: they become duplicates, not new leads
    run_all_jobs()
    assert db.scalar(select(func.count()).select_from(Lead)) == 4


def test_bad_files_rejected(client):
    for blob, name in [(b"\xff\xfe\x00bad", "x.csv"), (b"", "e.csv")]:
        r = client.post("/api/v1/imports", files={"file": (name, blob)}, headers=H)
        assert r.status_code == 422 and r.json()["error"]["code"] == "bad_file"


def test_mapping_requires_contact_field(client):
    up = upload(client, "Company,Name\nAcme,Jane\n")
    r = client.put(f"/api/v1/imports/{up['batch']['id']}/mapping", json={"mapping": {"company_name": "Company"}}, headers=H)
    assert r.status_code == 422


def test_retry_failed_rows(client, db):
    res = do_import(client, "Email,Company\nbad,A\nok@a.com,B\n")
    assert res["invalid_count"] == 1
    r = client.post(f"/api/v1/imports/{res['id']}/retry-failed", headers=H)
    assert r.status_code == 200
    run_all_jobs()
    res = client.get(f"/api/v1/imports/{res['id']}").json()
    assert res["invalid_count"] == 1 and res["created_count"] == 1      # still invalid; success not duplicated


def test_pagination_and_filters(client):
    rows = "Email\n" + "\n".join(f"u{i}@c{i}.com" for i in range(25))
    do_import(client, rows)
    p1 = client.get("/api/v1/leads?limit=10").json()
    assert len(p1["items"]) == 10 and p1["next_cursor"]
    p2 = client.get(f"/api/v1/leads?limit=10&cursor={p1['next_cursor']}").json()
    p3 = client.get(f"/api/v1/leads?limit=10&cursor={p2['next_cursor']}").json()
    ids = [i["id"] for p in (p1, p2, p3) for i in p["items"]]
    assert len(ids) == 25 == len(set(ids)) and p3["next_cursor"] is None
    assert len(client.get("/api/v1/leads?q=u7@").json()["items"]) == 1


def test_10k_rows_import(client):
    rows = "Email,Company,Website\n" + "\n".join(f"p{i}@co{i}.com,Co {i},co{i}.com" for i in range(10_000))
    t = time.time()
    up = upload(client, rows)
    assert time.time() - t < 15                       # upload/preview does not process rows
    bid = up["batch"]["id"]
    client.put(f"/api/v1/imports/{bid}/mapping", json={"mapping": up["batch"]["mapping"]}, headers=H)
    r = client.post(f"/api/v1/imports/{bid}/start", headers=H)
    assert r.status_code == 200 and r.json()["status"] == "queued"    # API returned before work done
    t = time.time(); run_all_jobs(); print(f"10k import worker time: {time.time() - t:.1f}s")
    assert client.get(f"/api/v1/imports/{bid}").json()["created_count"] == 10_000


def test_malformed_csv_edge_cases(client):
    csv_text = '﻿Email;Company\nüñí@exämple.com;"Café, Ltd"\n\n"multi\nline@x.com";Q\n'
    res = do_import(client, csv_text)
    assert res["total_rows"] == 2          # BOM stripped, ; delimiter sniffed, blank line skipped, UTF-8 kept
