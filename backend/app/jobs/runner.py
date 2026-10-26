import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import session_factory
from app.jobs import (
    handlers,  # noqa: F401  (registers job handlers)
    queue,
)
from app.services import mailsync, sending, voice

log = logging.getLogger("worker")


def main() -> None:
    configure_logging()
    settings = get_settings()
    log.info("worker started")
    last_mail_check = last_voice_purge = 0.0
    while True:
        with session_factory()() as db:
            worked = queue.run_one(db)
            worked = bool(sending.run_due(db)) or worked
            if time.monotonic() - last_mail_check > 15:  # cheap check; each account has its own poll interval
                last_mail_check = time.monotonic()
                mailsync.enqueue_due(db)
            if time.monotonic() - last_voice_purge > 300:  # delete expired dictations and any stray audio
                last_voice_purge = time.monotonic()
                voice.housekeeping(db)
        if not worked:
            time.sleep(settings.job_poll_seconds)


if __name__ == "__main__":
    main()
