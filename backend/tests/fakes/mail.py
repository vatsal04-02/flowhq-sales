"""Raw RFC 5322 message builders for tests."""
import uuid
from email.message import EmailMessage


def reply(from_addr: str, to_addr: str, body: str, subject: str = "Re: Quick idea", in_reply_to: str | None = None,
          references: str | None = None, message_id: str | None = None, headers: dict | None = None, html: str | None = None) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = from_addr, to_addr, subject
    m["Message-ID"] = message_id or f"<{uuid.uuid4().hex}@mail.test>"
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
    if references:
        m["References"] = references
    for k, v in (headers or {}).items():
        m[k] = v
    m.set_content(body)
    if html:
        m.add_alternative(html, subtype="html")
    return bytes(m)


def dsn(original_message_id: str, recipient: str, status: str = "5.1.1", action: str = "failed", from_addr: str = "MAILER-DAEMON@mx.test") -> bytes:
    b = f"bnd-{uuid.uuid4().hex[:8]}"
    return (
        f"From: {from_addr}\r\nTo: sender@flowhq.test\r\nSubject: Delivery Status Notification (Failure)\r\n"
        f"Message-ID: <{uuid.uuid4().hex}@mx.test>\r\nAuto-Submitted: auto-replied\r\nMIME-Version: 1.0\r\n"
        f'Content-Type: multipart/report; report-type=delivery-status; boundary="{b}"\r\n\r\n'
        f"--{b}\r\nContent-Type: text/plain\r\n\r\nYour message to {recipient} could not be delivered.\r\n\r\n"
        f"--{b}\r\nContent-Type: message/delivery-status\r\n\r\nReporting-MTA: dns; mx.test\r\n\r\n"
        f"Final-Recipient: rfc822; {recipient}\r\nAction: {action}\r\nStatus: {status}\r\nDiagnostic-Code: smtp; 550 {status} user unknown\r\n\r\n"
        f"--{b}\r\nContent-Type: message/rfc822\r\n\r\nMessage-ID: {original_message_id}\r\nFrom: sender@flowhq.test\r\nTo: {recipient}\r\n"
        f"Subject: Quick idea\r\n\r\noriginal body\r\n\r\n--{b}--\r\n"
    ).encode()


def plain_bounce(recipient: str, original_message_id: str | None = None, code: str = "550 5.1.1") -> bytes:
    orig = f"\r\nMessage-ID: {original_message_id}\r\n" if original_message_id else ""
    return (f"From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>\r\nTo: sender@flowhq.test\r\nSubject: Mail delivery failed: returning message to sender\r\n"
            f"Message-ID: <{uuid.uuid4().hex}@googlemail.com>\r\nX-Failed-Recipients: {recipient}\r\n\r\n"
            f"A message could not be delivered to {recipient}.\r\nThe error was: {code} The email account does not exist.\r\n{orig}").encode()
