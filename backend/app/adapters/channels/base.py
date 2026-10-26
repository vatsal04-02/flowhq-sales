import smtplib
import ssl
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol


@dataclass(frozen=True)
class Capabilities:
    can_send: bool
    can_receive: bool = False
    syncs_delivery: bool = False
    can_draft: bool = True
    requires_manual_action: bool = False
    required_permissions: tuple[str, ...] = ()


@dataclass
class Outbound:
    to: str
    from_email: str
    from_name: str
    subject: str
    body: str
    message_id: str
    in_reply_to: str | None = None
    list_unsubscribe_url: str | None = None


@dataclass
class SendResult:
    provider_message_id: str
    simulated: bool = False
    extra: dict = field(default_factory=dict)


class SendError(Exception):
    def __init__(self, msg: str, permanent: bool = False):
        super().__init__(msg)
        self.permanent = permanent


class ChannelAdapter(Protocol):
    capabilities: Capabilities

    def send(self, msg: Outbound, idempotency_key: str) -> SendResult: ...


class MockAdapter:
    """Never talks to a network. Results are flagged simulated and are reported separately in analytics."""
    capabilities = Capabilities(can_send=True, can_receive=True, syncs_delivery=True)
    fail_next: list[Exception] = []  # tests inject failures
    outbox: list[Outbound] = []

    def send(self, msg: Outbound, idempotency_key: str) -> SendResult:
        if MockAdapter.fail_next:
            raise MockAdapter.fail_next.pop(0)
        MockAdapter.outbox.append(msg)
        return SendResult(provider_message_id=f"mock-{uuid.uuid4().hex[:12]}", simulated=True)


class ManualAdapter:
    """LinkedIn / Instagram: drafts only. A human sends in their own browser; we never automate it."""
    capabilities = Capabilities(can_send=False, can_receive=False, can_draft=True, requires_manual_action=True)

    def send(self, msg, idempotency_key):  # pragma: no cover - guarded by the policy gate
        raise SendError("manual channel cannot send", permanent=True)


class SMTPAdapter:
    capabilities = Capabilities(can_send=True, can_receive=False, syncs_delivery=False,
                                required_permissions=("smtp credentials",))

    def __init__(self, host: str, port: int, username: str, password: str, security: str = "starttls"):
        self.host, self.port, self.username, self.password, self.security = host, port, username, password, security

    def send(self, msg: Outbound, idempotency_key: str) -> SendResult:
        m = EmailMessage()
        m["From"] = f"{msg.from_name} <{msg.from_email}>" if msg.from_name else msg.from_email
        m["To"] = msg.to
        m["Subject"] = msg.subject
        m["Date"] = formatdate(localtime=False)
        m["Message-ID"] = msg.message_id or make_msgid()
        if msg.in_reply_to:
            m["In-Reply-To"] = msg.in_reply_to
            m["References"] = msg.in_reply_to
        if msg.list_unsubscribe_url:
            m["List-Unsubscribe"] = f"<{msg.list_unsubscribe_url}>"
            m["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        m.set_content(msg.body)
        try:
            if self.security == "ssl":
                srv = smtplib.SMTP_SSL(self.host, self.port, timeout=30, context=ssl.create_default_context())
            else:
                srv = smtplib.SMTP(self.host, self.port, timeout=30)
            with srv:
                if self.security == "starttls":
                    srv.starttls(context=ssl.create_default_context())
                if self.username:
                    srv.login(self.username, self.password)
                srv.send_message(m)
        except smtplib.SMTPRecipientsRefused as exc:
            raise SendError(f"recipient refused: {exc}", permanent=True) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise SendError(f"{type(exc).__name__}: {exc}") from exc
        return SendResult(provider_message_id=m["Message-ID"])


def adapter_for(provider: str, creds: dict | None = None) -> ChannelAdapter:
    if provider == "mock":
        return MockAdapter()
    if provider == "smtp":
        c = creds or {}
        return SMTPAdapter(c["host"], int(c.get("port", 587)), c.get("username", ""), c.get("password", ""),
                           c.get("security", "starttls"))
    raise ValueError(f"unknown provider {provider}")


def capabilities_for(channel: str, provider: str | None) -> Capabilities:
    if channel in ("linkedin", "instagram"):
        return ManualAdapter.capabilities
    return MockAdapter.capabilities if provider == "mock" else SMTPAdapter.capabilities
