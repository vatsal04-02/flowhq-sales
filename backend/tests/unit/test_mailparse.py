from app.domain import mailparse as mp
from tests.fakes import mail


def test_plain_reply_threading_and_quote_stripping():
    raw = mail.reply("Asha <ASHA@BrightSmile.in>", "me@flowhq.test", "Sounds good, call me.\r\n\r\nOn Mon, 26 Oct 2026 at 10:00, Vatsal <me@flowhq.test> wrote:\r\n> Would it be worth a chat?\r\n> Please unsubscribe me if not",
                     in_reply_to="<abc@x>", references="<root@x> <abc@x>", message_id="<m1@mail.test>")
    p = mp.parse(raw)
    assert p.from_addr == "asha@brightsmile.in" and p.message_id == "<m1@mail.test>" and p.in_reply_to == "<abc@x>"
    assert p.references == ["<root@x>", "<abc@x>"] and p.body == "Sounds good, call me." and not p.is_auto and p.bounce is None


def test_html_only_reply_becomes_text_and_scripts_are_dropped():
    html = b"From: a@b.com\r\nTo: me@x.com\r\nSubject: Re: hi\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<div>Yes please<br>send details</div><script>alert(1)</script><style>p{}</style>"
    p = mp.parse(html)
    assert "Yes please" in p.body and "send details" in p.body and "alert" not in p.body and "p{}" not in p.body
    both = mail.reply("a@b.com", "me@x.com", "plain wins", html="<b>html</b>")
    assert mp.parse(both).body == "plain wins"          # plain text is preferred when both exist


def test_auto_replies_detected_by_header_and_subject():
    assert mp.parse(mail.reply("a@b.com", "me@x.com", "I am away", headers={"Auto-Submitted": "auto-replied"})).is_auto
    assert mp.parse(mail.reply("a@b.com", "me@x.com", "I am away", subject="Automatic reply: Quick idea")).is_auto
    assert mp.parse(mail.reply("a@b.com", "me@x.com", "Hi", headers={"X-Autoreply": "yes"})).is_auto
    assert not mp.parse(mail.reply("a@b.com", "me@x.com", "Thanks!")).is_auto
    assert not mp.parse(mail.reply("a@b.com", "me@x.com", "Hi", headers={"Auto-Submitted": "no"})).is_auto


def test_hard_and_soft_dsn():
    hard = mp.parse(mail.dsn("<orig1@flowhq.test>", "gone@acme.com")).bounce
    assert hard and hard.permanent is True and hard.recipient == "gone@acme.com" and hard.original_message_id == "<orig1@flowhq.test>" and hard.status == "5.1.1"
    soft = mp.parse(mail.dsn("<orig2@flowhq.test>", "full@acme.com", status="4.2.2", action="delayed")).bounce
    assert soft and soft.permanent is False
    assert mp.parse(mail.dsn("<o@x>", "g@a.com")).is_auto is False       # a bounce is a bounce, not an auto-reply


def test_plain_text_bounce_heuristic_and_human_false_positive():
    b = mp.parse(mail.plain_bounce("nobody@acme.com", "<orig3@flowhq.test>")).bounce
    assert b and b.permanent is True and b.recipient == "nobody@acme.com" and b.original_message_id == "<orig3@flowhq.test>"
    assert mp.parse(mail.plain_bounce("x@y.com", code="452 4.2.2 mailbox full")).bounce.permanent is False
    # a person who writes "undeliverable" in a subject is not a mail system
    assert mp.parse(mail.reply("asha@acme.com", "me@x.com", "Your last mail was undeliverable to my colleague", subject="undeliverable?")).bounce is None


def test_garbage_and_huge_input_never_raise():
    assert mp.parse(b"").from_addr is None
    mp.parse(b"\x00\x01\x02 not an email")           # must not raise
    big = mail.reply("a@b.com", "me@x.com", "x" * 50_000)
    assert len(mp.parse(big).body) <= mp.MAX_BODY
    assert mp.parse(b"From: a@b.com\r\nContent-Type: text/plain; charset=nonsense-99\r\n\r\nhello \xff\xfe").from_addr == "a@b.com"
