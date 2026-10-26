from datetime import timedelta

from app.jobs import queue

calls = []


@queue.handler("t_ok")
def _ok(db, job):
    calls.append(job.id)


@queue.handler("t_boom")
def _boom(db, job):
    raise RuntimeError("provider down")


def test_success(db):
    j = queue.enqueue(db, "t_ok", {}, None); db.commit()
    assert queue.run_one(db) is True
    db.refresh(j)
    assert j.state == "done" and j.attempts == 1
    assert queue.run_one(db) is False


def test_failure_backs_off_then_goes_dead_and_is_visible(db):
    j = queue.enqueue(db, "t_boom", {}, None, max_attempts=2); db.commit()
    queue.run_one(db); db.refresh(j)
    assert j.state == "pending" and "provider down" in j.last_error and j.run_after > queue.now()
    assert queue.run_one(db) is False                      # not yet due: nothing is lost, nothing runs early
    j.run_after = queue.now() - timedelta(seconds=1); db.commit()
    queue.run_one(db); db.refresh(j)
    assert j.state == "dead"                               # surfaced in /jobs?state=dead, retryable
    queue.retry_dead(db, j); db.commit()
    assert j.state == "pending" and j.attempts == 0


def test_crashed_worker_job_is_reclaimed_after_lease(db):
    j = queue.enqueue(db, "t_ok", {}, None); db.commit()
    claimed = queue.claim(db, lease_seconds=60)            # worker claims, then "crashes" (never finishes)
    assert claimed.id == j.id and queue.claim(db) is None  # lease holds: no double execution
    claimed.lease_until = queue.now() - timedelta(seconds=1); db.commit()
    again = queue.claim(db)
    assert again is not None and again.id == j.id and again.attempts == 2


def test_lease_expiring_forever_ends_dead(db):
    j = queue.enqueue(db, "t_ok", {}, None, max_attempts=1); db.commit()
    c = queue.claim(db); c.lease_until = queue.now() - timedelta(seconds=1); db.commit()
    assert queue.claim(db) is None
    db.refresh(j); assert j.state == "dead"


def test_unknown_job_type_fails_visibly(db):
    j = queue.enqueue(db, "nope", {}, None, max_attempts=1); db.commit()
    queue.run_one(db); db.refresh(j)
    assert j.state == "dead" and "no handler" in j.last_error
