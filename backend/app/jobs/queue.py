"""Durable Postgres job queue. Claiming uses FOR UPDATE SKIP LOCKED; crashed workers' leases expire
and the job is reclaimed. Handlers must be idempotent (at-least-once delivery)."""
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Job

Handler = Callable[[Session, Job], None]
HANDLERS: dict[str, Handler] = {}


def handler(job_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[job_type] = fn
        return fn
    return deco


def now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(db: Session, job_type: str, payload: dict[str, Any], workspace_id: uuid.UUID | None,
            max_attempts: int = 5, run_after: datetime | None = None) -> Job:
    job = Job(type=job_type, payload=payload, workspace_id=workspace_id,
              max_attempts=max_attempts, run_after=run_after or now())
    db.add(job)
    db.flush()
    return job


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** max(attempts - 1, 0), 3600))


def claim(db: Session, lease_seconds: int | None = None) -> Job | None:
    """Atomically claim one runnable job. Commits so the lease is visible to other workers."""
    lease = timedelta(seconds=lease_seconds or get_settings().job_lease_seconds)
    t = now()
    while True:
        job = db.scalars(
            select(Job)
            .where(or_(
                (Job.state == "pending") & (Job.run_after <= t),
                (Job.state == "running") & (Job.lease_until < t),
            ))
            .order_by(Job.run_after)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if job is None:
            db.rollback()
            return None
        if job.attempts >= job.max_attempts:  # lease expired too many times
            job.state = "dead"
            job.last_error = (job.last_error or "") + " | max attempts exhausted"
            db.commit()
            continue
        job.state = "running"
        job.attempts += 1
        job.lease_until = t + lease
        db.commit()
        return job


def run_one(db: Session) -> bool:
    job = claim(db)
    if job is None:
        return False
    fn = HANDLERS.get(job.type)
    try:
        if fn is None:
            raise RuntimeError(f"no handler for job type {job.type!r}")
        fn(db, job)
        db.refresh(job)
        job.state = "done"
        job.lease_until = None
        job.last_error = None
        db.commit()
    except Exception as exc:  # noqa: BLE001 - boundary: any handler failure is recorded
        db.rollback()
        job = db.get(Job, job.id)
        assert job is not None
        job.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        job.lease_until = None
        if job.attempts >= job.max_attempts:
            job.state = "dead"
        else:
            job.state = "pending"
            job.run_after = now() + backoff(job.attempts)
        db.commit()
    return True


def retry_dead(db: Session, job: Job) -> None:
    job.state = "pending"
    job.attempts = 0
    job.run_after = now()
    job.last_error = None
    db.flush()
