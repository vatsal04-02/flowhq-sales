import socket

from aiosmtpd.controller import Controller


class Sink:
    """Local SMTP server that records every accepted message. `reject` = recipient addresses to refuse at RCPT."""

    def __init__(self, port: int | None = None):
        self.messages: list[bytes] = []
        self.reject: set[str] = set()
        if port is None:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
        self.port = port
        self.ctrl = Controller(self, hostname="127.0.0.1", port=port)

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if address.lower() in self.reject:
            return "550 5.1.1 User unknown"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope.original_content or envelope.content)
        return "250 Message accepted for delivery"

    def start(self):
        self.ctrl.start()
        return self

    def stop(self):
        self.ctrl.stop()
