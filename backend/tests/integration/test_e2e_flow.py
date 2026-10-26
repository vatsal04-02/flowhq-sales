"""The first complete workflow: CSV import -> research -> qualify -> personalized draft -> approval -> test send ->
simulated reply -> dashboard update. Uses a local fixture website, the mock sandbox account, and no real LLM."""
import pytest
from sqlalchemy import select

from app.adapters.channels.base import MockAdapter
from app.models import Message
from tests.conftest import H
from tests.helpers import Site, biz_time, make_world, messages, run_sends


@pytest.fixture
def site():
    s = Site()
    yield s
    s.close()


def test_full_workflow(client, site, db):
    camp, batch, _ = make_world(client, site.url)
    cid = camp["id"]

    lead = client.get("/api/v1/leads").json()["items"][0]
    detail = client.get(f"/api/v1/leads/{lead['id']}").json()
    assert detail["research_status"] == "done"
    kinds = {e["finding"] for e in detail["evidence"]}
    assert {"Describes itself as", "Headline on its homepage", "Lists an offering or section"} <= kinds
    assert all(e["url"].startswith("http") and e["excerpt"] and e["retrieved_at"] for e in detail["evidence"])
    assert "alert(" not in " ".join(e["excerpt"] for e in detail["evidence"])         # script content never extracted
    assert detail["icp_class"] == "strong" and detail["icp_score"] >= 80
    assert {c["key"]: c["result"] for c in detail["icp_breakdown"]}["region"] == "match"

    msgs = messages(client, cid)
    assert [m["step"] for m in msgs] == [0, 1, 2] and all(m["status"] == "approved" for m in msgs)
    m0 = next(m for m in msgs if m["step"] == 0)
    assert 'your site says "Family dental clinic offering implants and orthodontics in Pune"' in m0["body"]
    assert m0["claims"] and m0["quality"]["verified_claims"] == 1 and "unsubscribe" not in m0["body"].lower()
    assert client.get(f"/api/v1/messages/{m0['id']}").json()["evidence"][0]["excerpt"].startswith("Family dental")

    r = client.post(f"/api/v1/campaigns/{cid}/launch", headers=H)
    assert r.status_code == 200 and r.json()["scheduled"] == 1
    assert run_sends(biz_time()) == 1
    assert len(MockAdapter.outbox) == 1
    out = MockAdapter.outbox[0]
    assert out.to == "asha@brightsmile.in" and "app.test/api/v1/u/" in out.body and "1 Example Street" in out.body
    assert out.list_unsubscribe_url.startswith("http://app.test/api/v1/u/")

    convs = client.get("/api/v1/conversations").json()
    assert len(convs) == 1 and convs[0]["last"]["direction"] == "out"
    ov = client.get("/api/v1/analytics/overview").json()["cards"]
    assert ov["messages_sent_simulated"]["value"] == 1 and ov["messages_sent_real"]["value"] == 0      # mock is never "real"
    assert ov["leads_contacted"]["value"] == 1

    r = client.post("/api/v1/sandbox/simulate-reply", json={"lead_id": lead["id"], "body": "Sounds interesting - can we book a call next week?"}, headers=H)
    assert r.json()["intent"] == "meeting_request"
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["status"] == "interested"
    assert run_sends(biz_time(10)) == 0 and len(MockAdapter.outbox) == 1          # replied -> follow-ups never go out
    conv = client.get(f"/api/v1/conversations/{convs[0]['id']}").json()
    assert [m["direction"] for m in conv["messages"]] == ["out", "in"] and conv["messages"][1]["simulated"] is True
    assert conv["messages"][1]["suggested_reply"]

    ts = client.get("/api/v1/analytics/timeseries?days=7").json()
    # the send used the test's simulated business-hours clock (may be "tomorrow"), the reply used the real clock
    assert len(ts) == 7 and sum(d["replies"] for d in ts) == 1 and sum(d["positive"] for d in ts) == 1
    ov = client.get("/api/v1/analytics/overview").json()
    c = ov["cards"]
    assert c["reply_rate"]["numerator"] == 1 and c["reply_rate"]["denominator"] == 1 and c["reply_rate"]["value"] == 100.0
    assert c["positive_reply_rate"]["numerator"] == 1 and c["opportunities"]["value"] == 1
    funnel = {f["stage"]: f["count"] for f in ov["funnel"]}
    assert funnel["Imported"] == 1 and funnel["Contacted"] == 1 and funnel["Replied"] == 1 and funnel["Opportunity"] == 1
    opp = client.get("/api/v1/opportunities").json()["items"][0]
    assert opp["stage"] == "engaged"
    client.patch(f"/api/v1/opportunities/{opp['id']}", json={"stage": "meeting_booked", "value": 5000}, headers=H)
    assert client.get(f"/api/v1/leads/{lead['id']}").json()["status"] == "meeting_booked"
    assert client.get("/api/v1/analytics/overview").json()["cards"]["meeting_conversion"]["numerator"] == 1


def test_follow_ups_go_out_on_schedule_in_thread(client, site, db):
    camp, *_ = make_world(client, site.url)
    client.post(f"/api/v1/campaigns/{camp['id']}/launch", headers=H)
    assert run_sends(biz_time()) == 1
    assert run_sends(biz_time(1)) == 0                               # day 3 not reached yet
    assert run_sends(biz_time(4)) == 1                               # step 1
    assert run_sends(biz_time(12)) == 1                              # step 2 (day 7 after day 3 + 4)
    assert run_sends(biz_time(30)) == 0                              # sequence complete
    out = MockAdapter.outbox
    assert len(out) == 3 and out[1].subject.startswith("Re: ") and out[1].in_reply_to == out[0].message_id
    assert out[2].in_reply_to == out[1].message_id
    sent = list(db.scalars(select(Message).where(Message.direction == "out").order_by(Message.created_at)))
    assert [m.state for m in sent] == ["sent"] * 3 and len({m.idempotency_key for m in sent}) == 3
