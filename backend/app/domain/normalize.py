"""Pure normalizers for imported lead fields. No I/O."""
import re
from urllib.parse import urlparse

import phonenumbers
from email_validator import EmailNotValidError, validate_email

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "live.com", "icloud.com", "aol.com", "proton.me", "protonmail.com", "yahoo.in",
    "rediffmail.com",
}


def blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def normalize_email(raw: str | None) -> str | None:
    raw = blank(raw)
    if not raw:
        return None
    try:
        return validate_email(raw, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        return None


def normalize_phone(raw: str | None, default_region: str | None = None) -> str | None:
    raw = blank(raw)
    if not raw:
        return None
    try:
        num = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def _host_and_path(raw: str) -> tuple[str, str] | None:
    raw = raw.strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", raw, re.I):
        raw = "https://" + raw
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        return None
    host = p.hostname.lower()
    if host.startswith("www."):
        host = host[4:]
    return host, p.path.rstrip("/")


def normalize_website(raw: str | None) -> str | None:
    raw = blank(raw)
    if not raw:
        return None
    hp = _host_and_path(raw)
    return f"https://{hp[0]}" if hp else None


def domain_of_website(url: str | None) -> str | None:
    hp = _host_and_path(url) if url else None
    return hp[0] if hp else None


def domain_of_email(email_norm: str | None) -> str | None:
    if not email_norm:
        return None
    d = email_norm.rsplit("@", 1)[-1]
    return None if d in FREE_EMAIL_DOMAINS else d


def _profile(raw: str | None, host: str, prefix: str) -> str | None:
    raw = blank(raw)
    if not raw:
        return None
    hp = _host_and_path(raw)
    if not hp or not (hp[0] == host or hp[0].endswith("." + host)):
        return None
    parts = [s for s in hp[1].split("/") if s]
    if prefix:
        if len(parts) < 2 or parts[0] != prefix:
            return None
        slug = parts[1]
    else:
        if not parts:
            return None
        slug = parts[0]
    return f"https://{host}/{prefix + '/' if prefix else ''}{slug.lower()}"


def normalize_linkedin(raw: str | None) -> str | None:
    # personal profiles (/in/) only; company pages are not person identifiers
    return _profile(raw, "linkedin.com", "in")


def normalize_instagram(raw: str | None) -> str | None:
    return _profile(raw, "instagram.com", "")


def csv_safe(value: object) -> str:
    """Neutralize spreadsheet formula injection for exported cells."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s
