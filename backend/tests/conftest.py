import os
import subprocess
import sys

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://flowhq:flowhq@localhost:5432/flowhq_test")
os.environ["DATABASE_URL"] = TEST_DB
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ALLOW_PRIVATE_FETCH"] = "true"   # fixtures are served from localhost; SSRF tests turn it off
os.environ["LLM_PROVIDER"] = "none"
os.environ["PUBLIC_BASE_URL"] = "http://app.test"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import hash_password
from app.db import get_engine, session_factory
from app.models import Membership, User, Workspace

H = {"X-Requested-With": "flowhq"}


@pytest.fixture(scope="session", autouse=True)
def migrated():
    root = os.path.dirname(os.path.dirname(__file__))
    run = lambda *a: subprocess.run([sys.executable, "-m", "alembic", "-x", f"url={TEST_DB}", *a],
                                    cwd=root, check=True, capture_output=True)
    run("downgrade", "base"); run("upgrade", "head")   # proves migrations apply from scratch
    yield


@pytest.fixture(autouse=True)
def clean_db(migrated):
    with get_engine().begin() as c:
        c.execute(text("TRUNCATE import_row_error, research_evidence, scheduled_action, message, conversation, generated_message, "
                       "campaign_lead, campaign, channel_account, opportunity, provider_event, ai_usage_record, lead, company, "
                       "import_batch, suppression_record, job, activity_log, audit_log, membership, user_account, workspace RESTART IDENTITY CASCADE"))
    from app.adapters.channels.base import MockAdapter
    from app.adapters.llm.base import set_llm_override
    MockAdapter.outbox.clear(); MockAdapter.fail_next.clear(); set_llm_override(None)
    yield


def make_user(email="op@example.com", password="correct-horse-battery", ws_name="WS1", ws_id=None):
    with session_factory()() as db:
        ws = db.get(Workspace, ws_id) if ws_id else Workspace(name=ws_name)
        db.add(ws)
        u = User(email=email, password_hash=hash_password(password))
        db.add(u); db.flush()
        db.add(Membership(workspace_id=ws.id, user_id=u.id, role="owner"))
        db.commit()
        return u.id, ws.id


def login(email="op@example.com", password="correct-horse-battery") -> TestClient:
    from app.main import app
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=H)
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def client():
    make_user()
    return login()


@pytest.fixture
def db():
    with session_factory()() as s:
        yield s


def upload(c: TestClient, csv_text: str, name="leads.csv", **form):
    r = c.post("/api/v1/imports", files={"file": (name, csv_text.encode(), "text/csv")}, data=form, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def run_all_jobs():
    from app.jobs import (
        handlers,  # noqa: F401
        queue,
    )
    n = 0
    while True:
        with session_factory()() as s:
            if not queue.run_one(s):
                return n
        n += 1


def do_import(c: TestClient, csv_text: str, mapping=None, **form):
    up = upload(c, csv_text, **form)
    bid = up["batch"]["id"]
    mapping = mapping or up["batch"]["mapping"]
    assert c.put(f"/api/v1/imports/{bid}/mapping", json={"mapping": mapping}, headers=H).status_code == 200
    assert c.post(f"/api/v1/imports/{bid}/start", headers=H).status_code == 200
    run_all_jobs()
    return c.get(f"/api/v1/imports/{bid}").json()
