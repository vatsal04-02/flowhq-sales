"""Named safety acceptance tests (PRD §14) that apply to the current milestone."""
from sqlalchemy import select

from app.domain.states import can_transition
from app.models import AuditLog, Lead, SuppressionRecord
from tests.conftest import H, do_import, login, make_user


def test_unauthenticated_requests_rejected():
    from fastapi.testclient import TestClient

    from app.main import app
    c = TestClient(app)
    assert c.get("/api/v1/leads").status_code == 401
    assert c.post("/api/v1/imports", headers=H).status_code == 401


def test_csrf_header_required_for_mutations(client):
    r = client.post("/api/v1/suppressions", json={"kind": "email", "value": "a@b.com"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf"


def test_cross_workspace_data_not_exposed(client):
    do_import(client, "Email,Company\nsecret@victim.com,Victim\n")
    lead_id = client.get("/api/v1/leads").json()["items"][0]["id"]
    batch_id = client.get("/api/v1/imports").json()[0]["id"]
    make_user("other@example.com", ws_name="WS2")
    other = login("other@example.com")
    assert other.get("/api/v1/leads").json()["items"] == []
    assert other.get(f"/api/v1/leads/{lead_id}").status_code == 404
    assert other.patch(f"/api/v1/leads/{lead_id}", json={"title": "x"}, headers=H).status_code == 404
    assert other.get(f"/api/v1/imports/{batch_id}").status_code == 404
    assert other.get(f"/api/v1/imports/{batch_id}/errors.csv").status_code == 404
    assert other.post(f"/api/v1/imports/{batch_id}/start", headers=H).status_code == 404


def test_same_email_allowed_in_different_workspaces(client):
    do_import(client, "Email\nshared@acme.com\n")
    make_user("other@example.com", ws_name="WS2")
    other = login("other@example.com")
    res = do_import(other, "Email\nshared@acme.com\n")
    assert res["created_count"] == 1 and res["duplicate_count"] == 0


def test_suppression_survives_reimport_and_lead_edits(client, db):
    assert client.post("/api/v1/suppressions", json={"kind": "email", "value": "NoThanks@Acme.com", "reason": "opt_out"},
                       headers=H).status_code == 200
    res = do_import(client, "Email,Company\nnothanks@acme.com,Acme\nfine@other.com,Other\n")
    assert res["suppressed_count"] == 1 and res["created_count"] == 1
    lead = db.scalars(select(Lead).where(Lead.email_norm == "nothanks@acme.com")).one()
    assert lead.status == "suppressed" and lead.opted_out
    # even if the lead row is hard-deleted, the suppression record still blocks a future import
    db.delete(lead); db.commit()
    res = do_import(client, "Email\nnothanks@acme.com\n")
    assert res["suppressed_count"] == 1


def test_domain_suppression_blocks_whole_company(client):
    client.post("/api/v1/suppressions", json={"kind": "domain", "value": "@blocked.com"}, headers=H)
    res = do_import(client, "Email\na@blocked.com\nb@blocked.com\nc@ok.com\n")
    assert res["suppressed_count"] == 2 and res["created_count"] == 1


def test_free_mail_domain_never_treated_as_company_domain(client):
    do_import(client, "Email,Company\na@gmail.com,A Co\nb@gmail.com,B Co\n")
    leads = client.get("/api/v1/leads").json()["items"]
    assert len({l["company_id"] for l in leads}) == 2          # not merged via gmail.com


def test_manual_suppression_marks_existing_lead_immediately(client):
    do_import(client, "Email\nx@acme.com\n")
    client.post("/api/v1/suppressions", json={"kind": "email", "value": "x@acme.com"}, headers=H)
    lead = client.get("/api/v1/leads").json()["items"][0]
    assert lead["status"] == "suppressed" and lead["opted_out"]


def test_stop_states_cannot_be_reactivated():
    for s in ("unsubscribed", "suppressed", "bounced"):
        for target in ("active_outreach", "approved", "needs_research", "qualified"):
            assert not can_transition(s, target)


def test_api_cannot_set_outreach_states_directly(client):
    do_import(client, "Email\nx@acme.com\n")
    lid = client.get("/api/v1/leads").json()["items"][0]["id"]
    for s in ("approved", "active_outreach", "replied", "converted"):
        r = client.patch(f"/api/v1/leads/{lid}", json={"status": s}, headers=H)
        assert r.status_code == 422, s
    r = client.patch(f"/api/v1/leads/{lid}", json={"status": "unsubscribed"}, headers=H)
    assert r.status_code == 200
    r = client.patch(f"/api/v1/leads/{lid}", json={"status": "needs_research"}, headers=H)
    assert r.status_code == 409                                   # cannot come back from unsubscribed


def test_unsubscribe_writes_suppression_and_audit(client, db):
    do_import(client, "Email\nx@acme.com\n")
    lid = client.get("/api/v1/leads").json()["items"][0]["id"]
    client.patch(f"/api/v1/leads/{lid}", json={"status": "unsubscribed"}, headers=H)
    assert db.scalars(select(SuppressionRecord).where(SuppressionRecord.value_norm == "x@acme.com")).first()
    assert "lead.status" in {a.action for a in db.scalars(select(AuditLog))}


def test_login_rejects_bad_password_and_no_secret_in_responses(client):
    from fastapi.testclient import TestClient

    from app.main import app
    r = TestClient(app).post("/api/v1/auth/login", json={"email": "op@example.com", "password": "nope"}, headers=H)
    assert r.status_code == 401
    assert "password_hash" not in client.get("/api/v1/me").text


def test_removing_suppression_requires_admin_and_is_audited(client, db):
    client.post("/api/v1/suppressions", json={"kind": "email", "value": "x@acme.com"}, headers=H)
    rec = client.get("/api/v1/suppressions").json()[0]
    assert client.delete(f"/api/v1/suppressions/{rec['id']}", headers=H).status_code == 200   # owner
    assert "suppression.remove" in {a.action for a in db.scalars(select(AuditLog))}
