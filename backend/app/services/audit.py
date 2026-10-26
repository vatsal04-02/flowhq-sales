import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import ActivityLog, AuditLog


def audit(db: Session, workspace_id: uuid.UUID | None, actor_id: uuid.UUID | None, action: str,
          target: str | None = None, **data: Any) -> None:
    db.add(AuditLog(workspace_id=workspace_id, actor_id=actor_id, action=action, target=target, data=data))


def activity(db: Session, workspace_id: uuid.UUID, lead_id: uuid.UUID | None, kind: str,
             **data: Any) -> None:
    db.add(ActivityLog(workspace_id=workspace_id, lead_id=lead_id, kind=kind, data=data))
