"""The only outbound fetcher for untrusted URLs. Blocks non-public addresses (SSRF), re-checks every
redirect, caps size/time, honours robots.txt. Residual risk: DNS rebinding between check and connect."""
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.core.config import get_settings

MAX_BYTES = 1_000_000


class FetchBlocked(Exception):
    pass


def assert_public_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchBlocked("only http(s) URLs are allowed")
    if get_settings().allow_private_fetch:
        return
    if p.port not in (None, 80, 443):
        raise FetchBlocked("non-standard port blocked")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchBlocked(f"cannot resolve host: {exc}") from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise FetchBlocked(f"blocked non-public address {info[4][0]}")


def fetch_html(url: str, timeout: float = 10.0) -> tuple[str, str]:
    """Returns (final_url, html). Raises FetchBlocked on policy violations or non-HTML."""
    s = get_settings()
    cur = url
    with httpx.Client(timeout=timeout, follow_redirects=False, headers={"User-Agent": s.fetch_user_agent}) as c:
        for _ in range(4):
            assert_public_url(cur)
            with c.stream("GET", cur) as r:
                if r.is_redirect:
                    cur = urljoin(cur, r.headers.get("location", ""))
                    continue
                if r.status_code >= 400:
                    raise FetchBlocked(f"HTTP {r.status_code}")
                if "html" not in r.headers.get("content-type", "").lower():
                    raise FetchBlocked("not an HTML page")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > MAX_BYTES:
                        break
                return cur, bytes(buf).decode(r.encoding or "utf-8", errors="replace")
    raise FetchBlocked("too many redirects")


def robots_allows(url: str) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        assert_public_url(robots_url)
        r = httpx.get(robots_url, timeout=5, headers={"User-Agent": get_settings().fetch_user_agent})
    except (FetchBlocked, httpx.HTTPError):
        return True  # unreachable robots.txt => no restrictions published
    if r.status_code >= 400:
        return True
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch("FlowHQBot", url)


class _Extract(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta_desc = ""
        self.headings: list[tuple[str, str]] = []
        self.links: list[tuple[str, str]] = []
        self.text: list[str] = []
        self._skip = 0
        self._tag: str | None = None
        self._buf: list[str] = []
        self._href: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "meta" and (a.get("name") or "").lower() in ("description", "og:description"):
            self.meta_desc = self.meta_desc or (a.get("content") or "").strip()
        elif tag == "meta" and (a.get("property") or "").lower() == "og:description":
            self.meta_desc = self.meta_desc or (a.get("content") or "").strip()
        elif tag in ("title", "h1", "h2", "h3"):
            self._tag, self._buf = tag, []
        elif tag == "a":
            self._href, self._buf = a.get("href"), []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip:
            self._skip -= 1
        elif tag == self._tag:
            t = " ".join("".join(self._buf).split())
            if tag == "title":
                self.title = self.title or t
            elif t:
                self.headings.append((tag, t))
            self._tag = None
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._buf).split())))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._tag or self._href is not None:
            self._buf.append(data)
        d = " ".join(data.split())
        if d:
            self.text.append(d)


def extract(html: str) -> dict:
    p = _Extract()
    p.feed(html)
    return {"title": p.title, "meta": p.meta_desc, "headings": p.headings, "links": p.links,
            "text": " ".join(p.text)[:20000]}
