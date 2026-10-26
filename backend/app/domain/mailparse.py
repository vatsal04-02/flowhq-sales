"""Pure RFC 5322 / RFC 3464 parsing for replies, auto-replies and bounces. Untrusted input: never raises on bad mail."""
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import message_from_string, policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

MAX_BODY = 5000
_ID = re.compile(r"<[^<>\s]+>")
_QUOTE_SPLIT = re.compile(r"\n\s*>|\n\s*on .{5,120} wrote:|\n-{2,}\s*original message|\n_{5,}\s*\n\s*from:|\nfrom: .{3,100}\nsent: ", re.I)
_AUTO_SUBJECT = re.compile(r"^\s*(auto(matic)?[\s-]*(reply|response)|autoreply|out of (the )?office|automatische antwort|réponse automatique)", re.I)
_BOUNCE_SUBJECT = re.compile(r"undeliver|delivery status notification|returned mail|mail delivery (failed|subsystem)|failure notice|delivery failure", re.I)
_EMAIL = re.compile(r"[\w.+'-]+@[\w-]+(?:\.[\w-]+)+")
_STATUS = re.compile(r"\b([245])\.\d{1,3}\.\d{1,3}\b")


@dataclass
class Bounce:
    permanent: bool | None  # True = hard (5.x.x), False = soft/delayed (4.x.x), None = could not tell
    recipient: str | None = None
    original_message_id: str | None = None
    status: str | None = None


@dataclass
class Parsed:
    message_id: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    from_addr: str | None = None
    subject: str = ""
    body: str = ""
    is_auto: bool = False
    bounce: Bounce | None = None
    date: datetime | None = None


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li"):
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML must not break sync
        return re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\n{3,}", "\n\n", "".join(p.out)).strip()


def strip_quoted(text: str) -> str:
    text = text.replace("\r\n", "\n")
    head = _QUOTE_SPLIT.split("\n" + text, maxsplit=1)[0]
    return re.sub(r"[ \t]+\n", "\n", head).strip()


def _ids(value) -> list[str]:
    return _ID.findall(str(value or ""))


def _body(msg: Message) -> str:
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        content = part.get_content()
        return html_to_text(content) if part.get_content_type() == "text/html" else content
    except Exception:  # noqa: BLE001 - bad charset / broken part: fall back to raw payload
        try:
            raw = msg.get_payload(decode=True)
            return raw.decode("utf-8", errors="replace") if raw else ""
        except Exception:  # noqa: BLE001
            return ""


def _dsn(msg: Message) -> Bounce | None:
    permanent, recipient, status, orig = None, None, None, None
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "message/delivery-status":
            for blk in part.get_payload() or []:
                if not isinstance(blk, Message):
                    continue
                action = str(blk.get("Action", "")).strip().lower()
                st = str(blk.get("Status", "")).strip()
                final = str(blk.get("Final-Recipient", "") or blk.get("Original-Recipient", ""))
                if final and not recipient:
                    m = _EMAIL.search(final)
                    recipient = m.group(0).lower() if m else None
                if st and not status:
                    status = st
                if action == "failed" and st.startswith("5"):
                    permanent = True
                elif (st.startswith("4") or action in ("delayed", "delivered", "relayed", "expanded")) and permanent is None:
                    permanent = False
        elif ct in ("message/rfc822", "text/rfc822-headers", "message/global-headers"):
            pl = part.get_payload()
            inner = pl[0] if isinstance(pl, list) and pl else None
            if isinstance(inner, Message):
                orig = orig or (_ids(inner.get("Message-ID")) or [None])[0]
            elif isinstance(pl, str):
                orig = orig or (_ids(message_from_string(pl).get("Message-ID")) or [None])[0]
    return Bounce(permanent, recipient, orig, status)


def _heuristic_bounce(msg: Message, from_addr: str | None, subject: str, body: str) -> Bounce | None:
    local = (from_addr or "").split("@")[0]
    if local not in ("mailer-daemon", "postmaster") and not _BOUNCE_SUBJECT.search(subject):
        return None
    if local not in ("mailer-daemon", "postmaster") and not re.search(r"daemon|postmaster|mail delivery|mail system", str(msg.get("From", "")), re.I):
        return None  # a human writing "undeliverable" in a subject is not a bounce
    failed = str(msg.get("X-Failed-Recipients", ""))
    m = _EMAIL.search(failed) or None
    recipient = m.group(0).lower() if m else None
    st = _STATUS.search(body)
    permanent = None if not st else st.group(1) == "5" if st.group(1) in "45" else None
    orig = re.search(r"Message-ID:\s*(<[^<>\s]+>)", body, re.I)
    return Bounce(permanent, recipient, orig.group(1) if orig else None, st.group(0) if st else None)


def parse(raw: bytes) -> Parsed:
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception:  # noqa: BLE001
        return Parsed()
    mids = _ids(msg.get("Message-ID"))
    refs = _ids(msg.get("References"))
    irt = (_ids(msg.get("In-Reply-To")) or [None])[0]
    _, addr = parseaddr(str(msg.get("From", "")))
    from_addr = addr.lower() or None
    subject = " ".join(str(msg.get("Subject", "")).split())[:300]
    try:
        date = parsedate_to_datetime(str(msg.get("Date"))) if msg.get("Date") else None
    except (TypeError, ValueError):
        date = None
    body_full = _body(msg)
    bounce = None
    if msg.get_content_type() == "multipart/report" and str(msg.get_param("report-type", "")).lower() == "delivery-status":
        bounce = _dsn(msg)
    else:
        bounce = _heuristic_bounce(msg, from_addr, subject, body_full)
    auto_sub = str(msg.get("Auto-Submitted", "")).strip().lower()
    is_auto = bool((auto_sub and auto_sub != "no") or msg.get("X-Autoreply") or msg.get("X-Autorespond")
                   or str(msg.get("Precedence", "")).strip().lower() in ("auto_reply", "auto-reply")
                   or _AUTO_SUBJECT.search(subject))
    return Parsed(message_id=mids[0] if mids else None, in_reply_to=irt, references=refs, from_addr=from_addr, subject=subject,
                  body=strip_quoted(body_full)[:MAX_BODY], is_auto=is_auto and bounce is None, bounce=bounce, date=date)
