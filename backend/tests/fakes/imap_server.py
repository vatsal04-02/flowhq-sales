"""A tiny IMAP server speaking enough of RFC 3501 (LOGIN, EXAMINE/SELECT, UID SEARCH, UID FETCH) to exercise the real
imaplib code path. Not a general IMAP server."""
import re
import socketserver
import threading
from datetime import datetime, timedelta, timezone


class FakeImap:
    def __init__(self, user="mailbox", password="s3cret", uidvalidity=1):
        self.user, self.password, self.uidvalidity = user, password, uidvalidity
        self.messages: list[tuple[int, bytes, datetime]] = []
        self.next_uid = 1
        self.commands: list[str] = []
        self.fail_connect = False
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                outer._serve(self)

        self.srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def add(self, raw: bytes, days_old: int = 0) -> int:
        uid = self.next_uid
        self.next_uid += 1
        self.messages.append((uid, raw, datetime.now(timezone.utc) - timedelta(days=days_old)))
        return uid

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()

    def config(self, **over) -> dict:
        return {"host": "127.0.0.1", "port": self.port, "username": self.user, "password": self.password, "security": "none", **over}

    def _serve(self, h):
        w = h.wfile.write
        if self.fail_connect:
            return
        w(b"* OK IMAP4rev1 fake ready\r\n")
        authed = False
        for line in h.rfile:
            text = line.decode(errors="replace").rstrip("\r\n")
            self.commands.append(text)
            tag, _, rest = text.partition(" ")
            cmd, _, args = rest.partition(" ")
            cmd = cmd.upper()
            if cmd == "CAPABILITY":
                w(b"* CAPABILITY IMAP4rev1\r\n" + tag.encode() + b" OK done\r\n")
            elif cmd == "LOGIN":
                parts = re.findall(r'"([^"]*)"|(\S+)', args)
                u, p = (a or b for a, b in parts[:2])
                if u == self.user and p == self.password:
                    authed = True
                    w(tag.encode() + b" OK logged in\r\n")
                else:
                    w(tag.encode() + b" NO [AUTHENTICATIONFAILED] bad credentials\r\n")
            elif not authed:
                w(tag.encode() + b" BAD login first\r\n")
            elif cmd in ("SELECT", "EXAMINE"):
                w(f"* {len(self.messages)} EXISTS\r\n* OK [UIDVALIDITY {self.uidvalidity}] ok\r\n".encode()
                  + tag.encode() + (b" OK [READ-ONLY] examined\r\n" if cmd == "EXAMINE" else b" OK [READ-WRITE] selected\r\n"))
            elif cmd == "UID":
                sub, _, a2 = args.partition(" ")
                if sub.upper() == "SEARCH":
                    uids = self._search(a2)
                    w(b"* SEARCH " + " ".join(map(str, uids)).encode() + b"\r\n" + tag.encode() + b" OK search done\r\n")
                elif sub.upper() == "FETCH":
                    uid = int(a2.split()[0])
                    hit = next(((i, m) for i, m in enumerate(self.messages, 1) if m[0] == uid), None)
                    if hit is None:
                        w(tag.encode() + b" OK fetch done\r\n")
                        continue
                    seq, (_, raw, _) = hit
                    w(f"* {seq} FETCH (UID {uid} BODY[]<0> {{{len(raw)}}}\r\n".encode() + raw + b")\r\n" + tag.encode() + b" OK fetch done\r\n")
                else:
                    w(tag.encode() + b" BAD unsupported\r\n")
            elif cmd == "NOOP":
                w(tag.encode() + b" OK\r\n")
            elif cmd == "LOGOUT":
                w(b"* BYE bye\r\n" + tag.encode() + b" OK logout\r\n")
                return
            else:
                w(tag.encode() + b" BAD unsupported\r\n")

    def _search(self, crit: str) -> list[int]:
        uids = [m[0] for m in self.messages]
        m = re.match(r"(\d+):\*", crit.replace("UID ", "").strip()) if crit.upper().startswith("UID") else None
        if m:
            n = int(m.group(1))
            hit = [u for u in uids if u >= n]
            return hit or ([max(uids)] if uids else [])  # RFC quirk: `n:*` always matches the newest message
        s = re.match(r"SINCE (\d+)-(\w+)-(\d+)", crit)
        if s:
            since = datetime.strptime(" ".join(s.groups()), "%d %b %Y").replace(tzinfo=timezone.utc)
            return [u for u, _, d in self.messages if d >= since]
        return uids  # ALL
