"""Operator CLI. Usage: python -m app.cli create-admin EMAIL PASSWORD [WORKSPACE_NAME]"""
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db import session_factory
from app.models import Membership, User, Workspace
from app.services.audit import audit


def create_admin(email: str, password: str, workspace: str = "FlowHQ") -> None:
    if len(password) < 12:
        raise SystemExit("password must be at least 12 characters")
    with session_factory()() as db:
        email = email.strip().lower()
        if db.scalars(select(User).where(User.email == email)).first():
            raise SystemExit("user already exists")
        ws = db.scalars(select(Workspace).order_by(Workspace.created_at)).first() or Workspace(name=workspace)
        db.add(ws)
        user = User(email=email, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
        audit(db, ws.id, user.id, "user.create_admin", email)
        db.commit()
        print(f"created owner {email} in workspace {ws.name}")


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] != "create-admin":
        raise SystemExit(__doc__)
    create_admin(*sys.argv[2:5])
