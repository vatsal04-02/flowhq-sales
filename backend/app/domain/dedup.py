"""Dedup rules (D9): auto-match only on exact normalized identifiers.
Company-name similarity never merges. Domain + same last name is only a *suggestion*."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Identity:
    email_norm: str | None = None
    phone_e164: str | None = None
    linkedin_url: str | None = None
    instagram_url: str | None = None


# Order = confidence order. Each tuple is (field, human-readable reason).
MATCH_KEYS = [
    ("email_norm", "email"),
    ("phone_e164", "phone"),
    ("linkedin_url", "linkedin"),
    ("instagram_url", "instagram"),
]


def match_keys(ident: Identity) -> list[tuple[str, str]]:
    return [(f, getattr(ident, f)) for f, _ in MATCH_KEYS if getattr(ident, f)]
