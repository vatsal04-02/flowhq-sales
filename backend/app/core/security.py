import base64
import hashlib
import hmac
import json
import time
import uuid

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError

from app.core.config import get_settings

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerificationError:
        return False


def _sign(payload: bytes) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def make_session_token(user_id: uuid.UUID, ttl_seconds: int | None = None) -> str:
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().session_ttl_hours * 3600
    body = base64.urlsafe_b64encode(
        json.dumps({"uid": str(user_id), "exp": int(time.time()) + ttl}).encode()
    ).decode()
    return f"{body}.{_sign(body.encode())}"


def read_session_token(token: str) -> uuid.UUID | None:
    try:
        body, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(sig, _sign(body.encode())):
            return None
        data = json.loads(base64.urlsafe_b64decode(body.encode()))
        if data["exp"] < time.time():
            return None
        return uuid.UUID(data["uid"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
