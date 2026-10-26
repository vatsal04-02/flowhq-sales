import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    s = get_settings()
    key = s.fernet_key or base64.urlsafe_b64encode(hashlib.sha256(("dev:" + s.secret_key).encode()).digest()).decode()
    return Fernet(key.encode())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
