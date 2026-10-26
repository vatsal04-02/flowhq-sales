import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import session_factory
from app.jobs import queue
from app.services import imports  # noqa: F401  (registers handlers)

log = logging.getLogger("worker")


def main() -> None:
    configure_logging()
    settings = get_settings()
    log.info("worker started")
    while True:
        with session_factory()() as db:
            worked = queue.run_one(db)
        if not worked:
            time.sleep(settings.job_poll_seconds)


if __name__ == "__main__":
    main()
