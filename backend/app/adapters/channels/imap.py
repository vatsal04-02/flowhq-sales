"""Read-only IMAP poller. Opens INBOX with EXAMINE and fetches with BODY.PEEK, so it never marks mail as read,
moves it or deletes it."""
import imaplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

MAX_FETCH_BYTES = 2_000_000


class ImapError(Exception):
    pass


@dataclass
class FetchResult:
    uidvalidity: int | None
    messages: list[tuple[int, bytes]] = field(default_factory=list)  # ascending by uid
    more: bool = False  # True when the batch limit was hit and more mail is waiting
    highest_uid: int | None = None  # newest UID in the mailbox (used to start the cursor past old history)


class ImapClient:
    def __init__(self, host: str, port: int = 993, username: str = "", password: str = "", security: str = "ssl", timeout: int = 30):
        self.host, self.port, self.username, self.password, self.security, self.timeout = host, port, username, password, security, timeout

    def _connect(self) -> imaplib.IMAP4:
        try:
            if self.security == "ssl":
                conn: imaplib.IMAP4 = imaplib.IMAP4_SSL(self.host, self.port, ssl_context=ssl.create_default_context(), timeout=self.timeout)
            else:
                conn = imaplib.IMAP4(self.host, self.port, timeout=self.timeout)
                if self.security == "starttls":
                    conn.starttls(ssl_context=ssl.create_default_context())
            conn.login(self.username, self.password)
            return conn
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ImapError(f"{type(exc).__name__}: {exc}"[:300]) from exc

    def check(self) -> int:
        """Login + EXAMINE only. Returns message count."""
        conn = self._connect()
        try:
            typ, data = conn.select("INBOX", readonly=True)
            if typ != "OK":
                raise ImapError("cannot open INBOX")
            return int(data[0])
        except (imaplib.IMAP4.error, OSError) as exc:
            raise ImapError(f"{type(exc).__name__}: {exc}"[:300]) from exc
        finally:
            self._logout(conn)

    @staticmethod
    def _logout(conn: imaplib.IMAP4) -> None:
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass

    def fetch_new(self, last_uid: int | None, uidvalidity: int | None, lookback_days: int = 7, limit: int = 100) -> FetchResult:
        conn = self._connect()
        try:
            typ, _ = conn.select("INBOX", readonly=True)
            if typ != "OK":
                raise ImapError("cannot open INBOX")
            validity = None
            _, vdata = conn.response("UIDVALIDITY")
            if vdata and vdata[0]:
                validity = int(vdata[0])
            fresh = last_uid is None or (uidvalidity is not None and validity != uidvalidity)
            if fresh:  # first run or the server renumbered the mailbox: only look back a bounded window
                since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
                typ, data = conn.uid("SEARCH", None, "SINCE", since)
            else:
                typ, data = conn.uid("SEARCH", None, "UID", f"{last_uid + 1}:*")
            if typ != "OK":
                raise ImapError("search failed")
            uids = sorted(int(u) for u in (data[0] or b"").split())
            highest = None
            if fresh:
                typ2, all_ids = conn.uid("SEARCH", None, "ALL")
                nums = [int(u) for u in (all_ids[0] or b"").split()] if typ2 == "OK" else []
                highest = max(nums) if nums else 0
            if not fresh:
                uids = [u for u in uids if u > (last_uid or 0)]  # `n:*` returns the newest message even if it is older than n
            more = len(uids) > limit
            out: list[tuple[int, bytes]] = []
            for uid in uids[:limit]:
                typ, parts = conn.uid("FETCH", str(uid), f"(BODY.PEEK[]<0.{MAX_FETCH_BYTES}>)")
                raw = next((p[1] for p in parts if isinstance(p, tuple) and len(p) > 1), None) if typ == "OK" and parts else None
                if raw:
                    out.append((uid, bytes(raw)))
                else:
                    out.append((uid, b""))  # keep the cursor moving; an empty body is skipped by the caller
            return FetchResult(validity, out, more, highest)
        except (imaplib.IMAP4.error, OSError, ValueError) as exc:
            raise ImapError(f"{type(exc).__name__}: {exc}"[:300]) from exc
        finally:
            self._logout(conn)


