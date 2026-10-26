from datetime import datetime, timezone

from app.domain import intent as I
from app.domain import message_validator as mv
from app.domain.policy import GateInput, check, next_window
from app.domain.research_extract import build_findings
from app.domain.scoring import Facts, evaluate


def test_scoring_unknown_is_not_failure_and_lowers_confidence():
    icp = {"industries": ["dental"], "regions": ["IN"], "keywords": ["implants", "orthodontics"]}
    r = evaluate(icp, Facts(industry=None, region=None, text="", evidence_count=0))
    assert r.score is None and r.klass == "insufficient"
    r = evaluate(icp, Facts(region="IN", text="dental clinic offering implants and orthodontics", evidence_count=3))
    assert r.klass == "strong" and r.score >= 80 and r.confidence == 100
    r = evaluate(icp, Facts(region=None, text="dental clinic offering implants and orthodontics", evidence_count=3))
    assert r.score >= 80 and r.confidence < 100                       # unknown region neither matches nor fails
    assert [c.result for c in r.criteria if c.key == "region"] == ["unknown"]


def test_scoring_exclusion_and_thresholds():
    r = evaluate({"keywords": ["x"], "exclude_keywords": ["franchise"]}, Facts(text="a franchise with x", evidence_count=3))
    assert r.score == 0 and r.klass == "unqualified" and r.excluded_by == "franchise"
    icp = {"keywords": ["alpha", "beta"], "industries": ["zzz"]}
    r = evaluate(icp, Facts(text="alpha beta", evidence_count=3), {"strong": 90, "possible": 20, "weak": 10})
    assert r.klass == "possible"                                       # thresholds are configurable


def test_validator_claims_and_numbers():
    ev = {"e1": {"kind": "verified", "excerpt": "We offer dental implants", "url": "u"},
          "e2": {"kind": "inferred", "excerpt": "probably growing fast", "url": "u"}}
    good, bad = mv.verify_claims([{"text": "a", "evidence_id": "e1", "quote": "dental implants"},
                                  {"text": "b", "evidence_id": "e1", "quote": "free whitening"},
                                  {"text": "c", "evidence_id": "e2", "quote": "growing fast"},
                                  {"text": "d", "evidence_id": "nope", "quote": "x"}], ev)
    assert [c["text"] for c in good] == ["a"] and len(bad) == 3         # inferred evidence never supports a claim
    body, removed = mv.strip_unsupported("Hi. b is great. Bye", [{"text": "b is great."}])
    assert "b is great" not in body and removed
    r = mv.validate("email", "Hello", "You grew 300% last year. " + "word " * 5, [])
    assert any("unverified figure" in e for e in r.errors)
    assert not mv.validate("email", "Hi", "I hope this email finds you well", []).ok
    assert any("longer" in e for e in mv.validate("linkedin", None, "x" * 301, []).errors)
    assert any("placeholder" in e for e in mv.validate("email", "S", "Hi {{first_name}}", []).errors)


def _gate(**kw):
    base = dict(now=datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc), kill_switch=False, campaign_status="active", campaign_lead_state="active",
                lead_status="approved", lead_opted_out=False, lead_region="IN", blocked_regions=["GB"], suppressed_reason=None, has_address=True,
                recipient="a@b.com", msg_status="approved", msg_hash="h", msg_approved_hash="h", channel_can_send=True, account_active=True,
                sent_today_account=0, account_daily_limit=30, sent_today_campaign=0, campaign_daily_limit=30, timezone="UTC",
                work_start=9, work_end=17, replied=False)
    return GateInput(**{**base, **kw})


def test_gate_blocks_each_unsafe_condition():
    assert check(_gate()).action == "allow"
    cases = {"kill_switch": True, "campaign_status": "paused", "lead_opted_out": True, "suppressed_reason": "email:opt_out", "replied": True,
             "lead_status": "unsubscribed", "lead_region": "GB", "recipient": None, "has_address": False, "msg_status": "draft",
             "msg_approved_hash": "old", "channel_can_send": False, "account_active": False, "campaign_lead_state": "stopped"}
    for k, v in cases.items():
        assert check(_gate(**{k: v})).action == "block", k
    assert check(_gate(kill_switch=True)).hold and not check(_gate(lead_opted_out=True)).hold


def test_gate_defers_for_limits_and_hours():
    d = check(_gate(sent_today_account=30))
    assert d.action == "defer" and d.until > datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
    sat = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)           # Saturday
    d = check(_gate(now=sat))
    assert d.action == "defer" and d.until.weekday() == 0 and d.until.hour == 9
    assert next_window(datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc), "UTC", 9, 17).day == 28


def test_intent_rules():
    assert I.classify("Please remove me from your list")[0] == "unsubscribe"
    assert I.classify("I am out of the office until Monday")[0] == "out_of_office"
    assert I.classify("Sounds great, can we book a call next week?")[0] == "meeting_request"
    assert I.classify("Not interested, thanks")[0] == "not_interested"
    assert I.classify("Can you send more details and pricing?")[0] == "requesting_info"
    assert I.classify("asdf")[0] == "unclear"
    assert I.classify("Thanks!\n> please unsubscribe me (quoted old text)")[0] == "unclear"


def test_research_extract_is_verbatim_and_dedups():
    pages = [{"url": "https://a.com", "title": "Acme", "meta": "We build robots", "headings": [("h1", "Robots for factories"), ("h2", "Welding"), ("h2", "Contact us"), ("h2", "Welding")], "text": "We build robots. Welding."}]
    f = build_findings(pages)
    ex = [x["excerpt"] for x in f]
    assert "We build robots" in ex and "Robots for factories" in ex and ex.count("Welding") == 1 and "Contact us" not in ex
    assert all(x["kind"] == "verified" for x in f)
