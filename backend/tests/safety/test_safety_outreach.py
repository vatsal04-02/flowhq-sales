"""PRD §14 safety acceptance tests for research, drafting and sending."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.adapters.channels.base import MockAdapter, SendError
from app.adapters.llm.base import FakeLLM, set_llm_override
from app.core.config import get_settings
from app.db import session_factory
from app.models import ChannelAccount, ScheduledAction, SuppressionRecord
from app.services import sending
from tests.conftest import H, login, make_user, run_all_jobs
from tests.helpers import INJECT, SITES, Site, biz_time, make_world, messages, run_sends


@pytest.fixture
def site():
    s = Site()
    yield s
    s.close()


def launch(client, camp):
    r = client.post(f"/api/v1/campaigns/{camp['id']}/launch", headers=H)
    assert r.status_code == 200, r.text


def lead_of(client):
    return client.get("/api/v1/leads").json()["items"][0]


def unsub_token(db):
    from app.models import Lead
    l = db.scalars(select(Lead)).first()
    return sending.make_unsub_token(l.workspace_id, l.id)


# ---- approval ----
def test_unapproved_draft_cannot_be_sent(client, site, db):
    camp, *_ = make_world(client, site.url, approve=False)
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    assert m0["status"] in ("draft", "needs_review")
    assert client.post(f"/api/v1/messages/{m0['id']}/send", headers=H).status_code == 409
    # launching with nothing approved is refused
    r = client.post(f"/api/v1/campaigns/{camp['id']}/launch", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_ready"
    # even a forged scheduled action is stopped by the gate at send time
    client.post(f"/api/v1/messages/{m0['id']}/approve", headers=H)
    launch(client, camp)
    client.post(f"/api/v1/messages/{m0['id']}/reject", headers=H)
    assert run_sends() == 0 and not MockAdapter.outbox


def test_edit_after_approval_invalidates_approval(client, site, db):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    r = client.patch(f"/api/v1/messages/{m0['id']}", json={"subject": m0["subject"], "body": m0["body"] + "\nP.S. new line"}, headers=H)
    assert r.json()["status"] in ("draft", "needs_review") and r.json()["approved_hash"] is None
    run_sends()
    assert not MockAdapter.outbox                                           # edited => must be re-approved
    assert "not approved" in client.get("/api/v1/actions?state=pending").json()[0]["last_error"]
    client.post(f"/api/v1/messages/{m0['id']}/approve", headers=H)
    run_sends(biz_time(1))
    assert len(MockAdapter.outbox) == 1


def test_injected_and_spammy_site_text_never_reaches_a_message(client):
    s = Site({"/": INJECT, "/robots.txt": ""})
    try:
        camp, *_ = make_world(client, s.url, approve=False, campaign={"icp": {"min_evidence": 1, "regions": ["IN"]}})
    finally:
        s.close()
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    low = m0["body"].lower()
    assert "ignore" not in low and "guarantee" not in low and "100%" not in low        # not quoted, not obeyed
    assert m0["claims"] == [] and m0["status"] == "needs_review"                       # falls back to conservative text, human review
    assert client.get(f"/api/v1/leads/{lead_of(client)['id']}").json()["evidence"]     # but the evidence is kept for the operator to inspect


def test_validator_blocks_spammy_text_even_if_a_human_adds_it(client, site):
    camp, *_ = make_world(client, site.url, approve=False)
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    r = client.patch(f"/api/v1/messages/{m0['id']}", json={"subject": m0["subject"], "body": m0["body"] + "\nWe guarantee 100% results!"}, headers=H)
    assert r.json()["status"] == "needs_review"
    r = client.post(f"/api/v1/messages/{m0['id']}/approve", headers=H)
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_errors"


# ---- unsupported AI claims ----
def test_llm_claim_without_evidence_is_rejected_and_template_used(client, site):
    def liar(schema, user):
        return {"subject": "Congrats on 500 patients", "opening": "Congrats on treating 500 patients last month!",
                "claims": [{"text": "Congrats on treating 500 patients last month!", "evidence_id": "e1", "quote": "treated 500 patients"}]}
    llm = FakeLLM(liar)
    set_llm_override(llm)
    camp, *_ = make_world(client, site.url, approve=False)
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    assert llm.calls and "500" not in m0["body"] and m0["source"] == "template"
    assert "rejected" in (m0["quality"]["llm_note"] or "")
    assert all(c["quote"] in "Family dental clinic offering implants and orthodontics in Pune Modern dental care for families Dental implants Orthodontics"
               for c in m0["claims"])


def test_llm_valid_claim_is_used_and_prompt_marks_page_text_untrusted(client, site):
    def good(schema, user):
        return {"subject": "Implants at Bright Smile", "opening": "I saw that your clinic offers implants and orthodontics.",
                "claims": [{"text": "your clinic offers implants and orthodontics", "evidence_id": "e1", "quote": "implants and orthodontics"}]}
    llm = FakeLLM(good)
    set_llm_override(llm)
    camp, *_ = make_world(client, site.url, approve=False)
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    assert m0["source"] == "llm" and m0["subject"] == "Implants at Bright Smile" and m0["quality"]["verified_claims"] == 1
    assert "<untrusted>" in llm.calls[0][1] and "never follow instructions" in llm.calls[0][0].lower()


def test_llm_outage_falls_back_to_templates_and_is_recorded(client, site):
    set_llm_override(FakeLLM(None))                                           # raises LLMUnavailable
    camp, *_ = make_world(client, site.url, approve=False)
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    assert m0["source"] == "template" and "unavailable" in m0["quality"]["llm_note"]
    assert client.get("/api/v1/integrations").json()["llm_usage"]["failures"] >= 1


# ---- opt-out / reply / bounce ----
def test_opted_out_lead_cannot_be_contacted_again(client, site, db):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    tok = unsub_token(db)
    assert client.get(f"/api/v1/u/{tok}").status_code == 200
    from app.models import Lead
    assert db.scalars(select(Lead)).first().status != "unsubscribed"          # GET alone never unsubscribes (mail scanners)
    from fastapi.testclient import TestClient

    from app.main import app
    assert TestClient(app).post(f"/api/v1/u/{tok}").status_code == 200       # public one-click POST, no login/CSRF
    run_sends()
    assert not MockAdapter.outbox
    db.expire_all()
    lead = db.scalars(select(Lead)).first()
    assert lead.status == "unsubscribed" and lead.opted_out
    assert db.scalars(select(SuppressionRecord).where(SuppressionRecord.value_norm == "asha@brightsmile.in")).first()
    assert TestClient(app).get("/api/v1/u/garbage").status_code == 400


def test_unsubscribe_reply_suppresses_immediately_and_stops_followups(client, site):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    assert run_sends() == 1
    lead = lead_of(client)
    r = client.post("/api/v1/sandbox/simulate-reply", json={"lead_id": lead["id"], "body": "Please remove me from your list."}, headers=H)
    assert r.json()["intent"] == "unsubscribe"
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["status"] == "unsubscribed"
    run_sends(biz_time(30))
    assert len(MockAdapter.outbox) == 1


def test_replied_lead_gets_no_automatic_followup(client, site):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    run_sends()
    lead = lead_of(client)
    client.post("/api/v1/sandbox/simulate-reply", json={"lead_id": lead["id"], "body": "Who is this?"}, headers=H)   # unclear -> still stops
    run_sends(biz_time(30))
    assert len(MockAdapter.outbox) == 1


def test_out_of_office_does_not_stop_sequence(client, site):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    run_sends()
    client.post("/api/v1/sandbox/simulate-reply", json={"lead_id": lead_of(client)["id"], "body": "I am out of the office until next week."}, headers=H)
    assert run_sends(biz_time(5)) == 1


def test_bounce_suppresses_and_stops(client, site, db):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    run_sends()
    lead = lead_of(client)
    assert client.post(f"/api/v1/sandbox/simulate-bounce?lead_id={lead['id']}", headers=H).json()["processed"] is True
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["status"] == "bounced"
    assert db.scalars(select(SuppressionRecord).where(SuppressionRecord.reason == "bounce")).first()
    run_sends(biz_time(30))
    assert len(MockAdapter.outbox) == 1


def test_duplicate_provider_events_are_ignored(client, site, db):
    camp, *_ = make_world(client, site.url)
    launch(client, camp); run_sends()
    lead = lead_of(client)
    body = {"lead_id": lead["id"], "body": "Interested!", "external_id": "evt-1"}
    assert client.post("/api/v1/sandbox/simulate-reply", json=body, headers=H).json()["duplicate_ignored"] is False
    assert client.post("/api/v1/sandbox/simulate-reply", json=body, headers=H).json()["duplicate_ignored"] is True
    conv = client.get("/api/v1/conversations").json()[0]
    assert len([m for m in client.get(f"/api/v1/conversations/{conv['id']}").json()["messages"] if m["direction"] == "in"]) == 1


def test_human_reclassification_unsubscribe_takes_effect(client, site):
    camp, *_ = make_world(client, site.url)
    launch(client, camp); run_sends()
    lead = lead_of(client)
    client.post("/api/v1/sandbox/simulate-reply", json={"lead_id": lead["id"], "body": "hmm okay"}, headers=H)
    conv = client.get("/api/v1/conversations").json()[0]
    inbound = [m for m in client.get(f"/api/v1/conversations/{conv['id']}").json()["messages"] if m["direction"] == "in"][0]
    assert inbound["intent"] == "unclear"
    client.post(f"/api/v1/conversations/{conv['id']}/classify", json={"message_id": inbound["id"], "intent": "unsubscribe"}, headers=H)
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["status"] == "unsubscribed"
    r = client.post(f"/api/v1/conversations/{conv['id']}/reply", json={"body": "hello again"}, headers=H)
    assert r.status_code == 409 and r.json()["error"]["code"] == "lead_suppressed"


# ---- pause / kill switch / failures ----
def test_paused_campaign_never_sends_and_resumes_without_loss(client, site):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    client.post(f"/api/v1/campaigns/{camp['id']}/pause", headers=H)
    run_sends()
    assert not MockAdapter.outbox
    actions = client.get("/api/v1/actions?state=pending").json()
    assert len(actions) == 1 and "paused" in actions[0]["last_error"]          # held, not lost
    client.post(f"/api/v1/campaigns/{camp['id']}/resume", headers=H)
    assert run_sends(biz_time(0) + timedelta(hours=1)) == 1 and len(MockAdapter.outbox) == 1


def test_global_kill_switch_blocks_everything(client, site):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    client.post("/api/v1/workspace/kill-switch", json={"on": True}, headers=H)
    run_sends()
    assert not MockAdapter.outbox
    client.post("/api/v1/workspace/kill-switch", json={"on": False}, headers=H)
    assert run_sends(biz_time() + timedelta(hours=1)) == 1


def test_provider_outage_retries_without_duplicates(client, site, db):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    MockAdapter.fail_next[:] = [SendError("smtp down"), SendError("smtp down")]
    t = biz_time()
    assert run_sends(t, rounds=1) == 1 and not MockAdapter.outbox            # action stays queued with last_error
    a = db.scalars(select(ScheduledAction)).first(); db.refresh(a)
    assert a.state == "pending" and a.retry_count == 1 and "smtp down" in a.last_error
    assert run_sends(t + timedelta(hours=1), rounds=1) == 1                   # still failing
    assert run_sends(t + timedelta(hours=2), rounds=1) == 1                   # recovered
    assert len(MockAdapter.outbox) == 1
    from app.models import Message
    assert len(list(db.scalars(select(Message).where(Message.direction == "out")))) == 1


def test_permanent_failure_is_visible_and_recoverable(client, site, db):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    MockAdapter.fail_next[:] = [SendError("550 mailbox unavailable", permanent=True)]
    run_sends(rounds=1)
    failed = client.get("/api/v1/actions?state=problem").json()
    assert len(failed) == 1 and failed[0]["state"] == "failed" and "550" in failed[0]["last_error"]
    assert client.get("/api/v1/analytics/attention").json()["failed_actions"] == 1
    assert client.post(f"/api/v1/actions/{failed[0]['id']}/retry", headers=H).status_code == 200
    assert run_sends(biz_time(1)) == 1 and len(MockAdapter.outbox) == 1


def test_crash_after_send_is_never_resent(client, site, db):
    """Worker dies after the provider accepted but before the result was recorded."""
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    with session_factory()() as s:
        a = s.scalars(select(ScheduledAction)).first()
        a.state, a.lease_until = "claiming", datetime.now(timezone.utc) - timedelta(minutes=1)     # expired lease
        from app.models import Message
        s.add(Message(workspace_id=a.workspace_id, conversation_id=_conv(s, a), lead_id=a.lead_id, campaign_id=a.campaign_id, direction="out",
                      channel="email", body="x", state="sending", idempotency_key=a.idempotency_key))
        s.commit()
    run_sends()
    assert not MockAdapter.outbox                                            # no second send
    a = client.get("/api/v1/actions?state=problem").json()
    assert len(a) == 1 and a[0]["state"] == "needs_manual_check"
    assert client.post(f"/api/v1/actions/{a[0]['id']}/resolve", json={"was_sent": True}, headers=H).status_code == 200
    run_sends(biz_time(1))
    assert not MockAdapter.outbox


def _conv(s, a):
    from app.models import Conversation
    c = Conversation(workspace_id=a.workspace_id, lead_id=a.lead_id, campaign_id=a.campaign_id, channel="email")
    s.add(c); s.flush()
    return c.id


# ---- channel / policy rules ----
def test_channel_without_send_capability_cannot_send(client, site, db):
    camp, *_ = make_world(client, site.url, campaign={"channels": ["email", "linkedin"]})
    launch(client, camp)
    li = [m for m in messages(client, camp["id"], channel="linkedin")]
    assert li and all(m["channel"] == "linkedin" and len(m["body"]) <= 300 for m in li)
    r = client.post(f"/api/v1/messages/{li[0]['id']}/send", headers=H)
    assert r.status_code == 409 and r.json()["error"]["code"] == "manual_channel"
    with session_factory()() as s:                                            # forged action: the gate still refuses
        base = s.scalars(select(ScheduledAction)).first()
        s.add(ScheduledAction(workspace_id=base.workspace_id, lead_id=base.lead_id, campaign_id=base.campaign_id, generated_message_id=li[0]["id"],
                              step=0, channel="linkedin", run_at=datetime.now(timezone.utc), idempotency_key="forged"))
        s.commit()
    run_sends()
    assert all("linkedin" not in str(o) for o in MockAdapter.outbox)
    with session_factory()() as s:
        f = s.scalars(select(ScheduledAction).where(ScheduledAction.idempotency_key == "forged")).one()
        assert f.state == "cancelled" and "cannot send" in f.last_error


def test_manual_queue_mark_sent_counts_as_manual_not_real(client, site):
    camp, *_ = make_world(client, site.url, campaign={"channels": ["linkedin"]}, mock=False)
    q = client.get("/api/v1/manual-queue").json()
    assert q["items"] and "never logs into" in q["note"]
    mid = next(i["id"] for i in q["items"] if i["step"] == 0)
    assert client.post(f"/api/v1/messages/{mid}/mark-sent", headers=H).status_code == 200
    c = client.get("/api/v1/analytics/overview").json()["cards"]
    assert c["messages_sent_manual"]["value"] == 1 and c["messages_sent_real"]["value"] == 0 and c["leads_contacted"]["value"] == 1


def test_blocked_region_is_not_contacted(client, site):
    csv = "Company,First Name,Email,Website,Country\nLondon Dental,Tom,tom@london.example,london.example,GB\n"
    camp, *_ = make_world(client, site.url, csv_text=csv, campaign={"icp": {"keywords": ["implants"]}})
    launch(client, camp)
    run_sends()
    assert not MockAdapter.outbox
    assert "blocked" in client.get("/api/v1/actions?state=cancelled").json()[0]["last_error"]


def test_daily_limit_defers_not_drops(client, site):
    csv = "Company,First Name,Email,Website,Country\nA,A,a@aa.in,aa.in,IN\nB,B,b@bb.in,bb.in,IN\n"
    camp, *_ = make_world(client, site.url, csv_text=csv, campaign={"daily_limit": 1})
    launch(client, camp)
    assert run_sends(biz_time(), rounds=1) == 2 and len(MockAdapter.outbox) == 1
    pend = client.get("/api/v1/actions?state=pending").json()
    assert [a for a in pend if a["step"] == 0 and "daily" in (a["last_error"] or "")]       # the second lead is deferred, not dropped


def test_outside_working_hours_is_deferred(client, site):
    camp, *_ = make_world(client, site.url)
    launch(client, camp)
    night = biz_time().replace(hour=22)
    assert run_sends(night, rounds=1) == 1 and not MockAdapter.outbox
    a = client.get("/api/v1/actions?state=pending").json()[0]
    assert "working hours" in a["last_error"]


def test_launch_requires_address_and_account(client, site):
    camp, *_ = make_world(client, site.url, campaign={"physical_address": ""})
    r = client.post(f"/api/v1/campaigns/{camp['id']}/launch", headers=H)
    assert r.status_code == 422 and any(c["key"] == "address" for c in r.json()["error"]["details"]["checks"])


# ---- research safety ----
def test_ssrf_private_addresses_blocked(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "allow_private_fetch", False)
    for url in ("http://127.0.0.1:8000", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5", "http://localhost"):
        from app.adapters.fetch.safe_fetcher import FetchBlocked, assert_public_url
        with pytest.raises(FetchBlocked):
            assert_public_url(url)
    from app.adapters.fetch.safe_fetcher import FetchBlocked, assert_public_url
    with pytest.raises(FetchBlocked):
        assert_public_url("file:///etc/passwd")
    with pytest.raises(FetchBlocked):
        assert_public_url("http://example.com:8080")


def test_research_respects_robots_txt(client):
    s = Site({"/": SITES["/"], "/robots.txt": "User-agent: *\nDisallow: /\n"})
    try:
        make_world(client, s.url, approve=False, research=False)
        lead = lead_of(client)
        client.post(f"/api/v1/leads/{lead['id']}/research", headers=H)
        run_all_jobs()
    finally:
        s.close()
    d = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert d["research_status"] == "failed" and not d["evidence"]
    assert any("robots" in str(t["data"]) for t in d["timeline"])


def test_insufficient_research_goes_to_manual_review_not_guesswork(client):
    s = Site({"/": "<html><body><p>Hi</p></body></html>", "/robots.txt": ""})
    try:
        camp, *_ = make_world(client, s.url, approve=False)
    finally:
        s.close()
    cl = client.get(f"/api/v1/campaigns/{camp['id']}/leads").json()[0]
    assert cl["icp_class"] == "insufficient" and cl["icp_score"] is None
    assert messages(client, camp["id"]) == []                                  # nothing generated by default
    client.post(f"/api/v1/campaigns/{camp['id']}/generate-messages", json={"include_insufficient": True}, headers=H); run_all_jobs()
    m0 = next(m for m in messages(client, camp["id"]) if m["step"] == 0)
    assert m0["status"] == "needs_review" and m0["claims"] == [] and "conservative" in " ".join(m0["quality"]["warnings"])


# ---- tenancy & secrets ----
def test_other_workspace_cannot_touch_campaign_data(client, site):
    camp, *_ = make_world(client, site.url)
    mid = messages(client, camp["id"])[0]["id"]
    launch(client, camp); run_sends()
    conv_id = client.get("/api/v1/conversations").json()[0]["id"]
    make_user("other@example.com", ws_name="WS2")
    o = login("other@example.com")
    assert o.get(f"/api/v1/campaigns/{camp['id']}").status_code == 404
    assert o.get(f"/api/v1/messages/{mid}").status_code == 404
    assert o.post(f"/api/v1/messages/{mid}/approve", headers=H).status_code == 404
    assert o.post(f"/api/v1/campaigns/{camp['id']}/pause", headers=H).status_code == 404
    assert o.get(f"/api/v1/conversations/{conv_id}").status_code == 404
    assert o.post(f"/api/v1/conversations/{conv_id}/reply", json={"body": "x"}, headers=H).status_code == 404
    assert o.get("/api/v1/messages").json() == [] and o.get("/api/v1/conversations").json() == []
    assert o.get("/api/v1/analytics/overview").json()["cards"]["messages_sent_simulated"]["value"] == 0
    assert o.post("/api/v1/campaigns", json={"name": "x", "channel_account_id": client.get("/api/v1/integrations").json()["accounts"][0]["id"]}, headers=H).status_code == 422


def test_smtp_credentials_encrypted_and_never_returned(client, db):
    r = client.post("/api/v1/integrations/smtp", json={"name": "Gmail", "from_email": "me@x.com", "host": "smtp.x.com", "username": "me", "password": "S3CRET-PW"}, headers=H)
    assert r.status_code == 200 and "S3CRET-PW" not in r.text
    assert "S3CRET-PW" not in client.get("/api/v1/integrations").text
    raw = db.scalars(select(ChannelAccount)).first().credentials_enc
    assert raw and "S3CRET-PW" not in raw
