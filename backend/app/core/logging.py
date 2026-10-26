import json
import logging
import re
import sys
from datetime import datetime, timezone

_SECRET_KV = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|api[_-]?key|cookie)(\"?\s*[:=]\s*\"?)([^\s\",;]+)"
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def redact(text: str) -> str:
    text = _SECRET_KV.sub(r"\1\2[REDACTED]", text)
    return _EMAIL.sub(r"[email]@\1", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
