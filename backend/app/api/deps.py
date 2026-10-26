import uuid
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import read_session_token
from app.db import get_db
from app.models import Membership, User

COOKIE = "flowhq_session"
ROLE_RANK = {"rep": 1, "admin": 2, "owner": 3}


@dataclass
class Ctx:
    db: Session
    user: User
    workspace_id: uuid.UUID
    role: str


def err(status: int, code: str, message: str, **details) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": message, "details": details}})


def get_ctx(request: Request, db: Session = Depends(get_db),
            x_requested_with: str | None = Header(default=None)) -> Ctx:
    # CSRF defence for cookie auth: browsers cannot add this header cross-site without CORS preflight.
    if request.method not in ("GET", "HEAD", "OPTIONS") and x_requested_with != "flowhq":
        raise err(403, "csrf", "missing X-Requested-With header")
    token = request.cookies.get(COOKIE)
    uid = read_session_token(token) if token else None
    user = db.get(User, uid) if uid else None
    if user is None or not user.is_active:
        raise err(401, "unauthenticated", "login required")
    mem = db.scalars(select(Membership).where(Membership.user_id == user.id)
                     .order_by(Membership.created_at)).first()
    if mem is None:
        raise err(403, "no_workspace", "user has no workspace")
    return Ctx(db=db, user=user, workspace_id=mem.workspace_id, role=mem.role)


def require_admin(ctx: Ctx = Depends(get_ctx)) -> Ctx:
    if ROLE_RANK.get(ctx.role, 0) < ROLE_RANK["admin"]:
        raise err(403, "forbidden", "admin role required")
    return ctx
