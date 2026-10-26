import pytest

from app.core.logging import redact
from app.domain import normalize as n
from app.domain.states import IllegalTransition, can_transition, check_transition


def test_email():
    assert n.normalize_email("  Jane.Doe@Example.COM ") == "jane.doe@example.com"
    assert n.normalize_email("not-an-email") is None
    assert n.normalize_email("") is None


def test_phone():
    assert n.normalize_phone("+91 98765 43210") == "+919876543210"
    assert n.normalize_phone("098765 43210", "IN") == "+919876543210"
    assert n.normalize_phone("12345") is None


def test_urls():
    assert n.normalize_website("WWW.Acme.com/about?x=1") == "https://acme.com"
    assert n.normalize_website("nonsense") is None
    assert n.normalize_linkedin("http://www.linkedin.com/in/Jane-Doe/?utm=1") == "https://linkedin.com/in/jane-doe"
    assert n.normalize_linkedin("https://linkedin.com/company/acme") is None
    assert n.normalize_instagram("https://instagram.com/Acme.Co/") == "https://instagram.com/acme.co"
    assert n.domain_of_email("a@gmail.com") is None
    assert n.domain_of_email("a@acme.com") == "acme.com"


def test_csv_safe():
    for bad in ("=1+1", "+cmd", "-x", "@SUM(A1)"):
        assert n.csv_safe(bad).startswith("'")
    assert n.csv_safe("ok") == "ok"


def test_transitions():
    check_transition("imported", "needs_research")
    assert not can_transition("imported", "active_outreach")
    for dead in ("unsubscribed", "suppressed", "bounced"):
        assert not can_transition(dead, "active_outreach")
    with pytest.raises(IllegalTransition):
        check_transition("imported", "converted")


def test_log_redaction():
    out = redact('login password=hunter2 token: abc123 mail bob@acme.com')
    assert "hunter2" not in out and "abc123" not in out and "bob@" not in out
