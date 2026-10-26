import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _id() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _ws() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("workspace.id"), nullable=False, index=True)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Workspace(Base, Timestamps):
    __tablename__ = "workspace"
    id: Mapped[uuid.UUID] = _id()
    name: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base, Timestamps):
    __tablename__ = "user_account"
    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(Base, Timestamps):
    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_account.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="rep")  # owner | admin | rep


class Company(Base, Timestamps):
    __tablename__ = "company"
    __table_args__ = (
        Index("uq_company_ws_domain", "workspace_id", "domain", unique=True,
              postgresql_where=text("domain IS NOT NULL AND deleted_at IS NULL")),
    )
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    name: Mapped[str | None] = mapped_column(String(300))
    domain: Mapped[str | None] = mapped_column(String(253))
    website: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(300))
    industry: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportBatch(Base, Timestamps):
    __tablename__ = "import_batch"
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"))
    filename: Mapped[str] = mapped_column(String(300))
    file_sha256: Mapped[str] = mapped_column(String(64))
    file_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    headers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    mapping: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    default_region: Mapped[str | None] = mapped_column(String(2))  # phone parsing, e.g. "IN"
    status: Mapped[str] = mapped_column(String(20), default="uploaded")
    # uploaded | mapped | queued | running | completed | failed
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    next_row: Mapped[int] = mapped_column(Integer, default=1)  # resume cursor (1-based data row)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, default=0)
    suppressed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class ImportRowError(Base, Timestamps):
    __tablename__ = "import_row_error"
    __table_args__ = (UniqueConstraint("batch_id", "row_number"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("import_batch.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20))  # invalid | duplicate
    reason: Mapped[str] = mapped_column(String(500))
    existing_lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class Lead(Base, Timestamps):
    __tablename__ = "lead"
    __table_args__ = (
        Index("uq_lead_ws_email", "workspace_id", "email_norm", unique=True,
              postgresql_where=text("email_norm IS NOT NULL AND deleted_at IS NULL")),
        Index("uq_lead_batch_row", "import_batch_id", "import_row", unique=True,
              postgresql_where=text("import_batch_id IS NOT NULL")),
        Index("ix_lead_ws_created", "workspace_id", "created_at", "id"),
        Index("ix_lead_ws_phone", "workspace_id", "phone_e164"),
        Index("ix_lead_ws_linkedin", "workspace_id", "linkedin_url"),
        Index("ix_lead_ws_instagram", "workspace_id", "instagram_url"),
    )
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("company.id"), index=True)
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("import_batch.id"))
    import_row: Mapped[int | None] = mapped_column(Integer)
    first_name: Mapped[str | None] = mapped_column(String(200))
    last_name: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(320))  # as supplied
    email_norm: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    instagram_url: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    region: Mapped[str | None] = mapped_column(String(2))  # ISO country, drives send policy
    lawful_basis: Mapped[str | None] = mapped_column(String(500))
    custom: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)  # original CSV values
    status: Mapped[str] = mapped_column(String(30), default="imported", index=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user_account.id"))
    possible_duplicate_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    research_status: Mapped[str] = mapped_column(String(20), default="none", server_default="none")  # none|done|insufficient|failed
    research_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    icp_score: Mapped[int | None] = mapped_column(Integer)
    icp_class: Mapped[str | None] = mapped_column(String(20))  # strong|possible|weak|unqualified|insufficient
    icp_confidence: Mapped[int | None] = mapped_column(Integer)
    icp_breakdown: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SuppressionRecord(Base, Timestamps):
    """Keyed on normalized values, independent of lead rows, so it survives edits/re-imports."""
    __tablename__ = "suppression_record"
    __table_args__ = (UniqueConstraint("workspace_id", "kind", "value_norm"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    kind: Mapped[str] = mapped_column(String(10))  # email | domain | phone
    value_norm: Mapped[str] = mapped_column(String(320))
    reason: Mapped[str] = mapped_column(String(200))  # opt_out | bounce | manual | complaint
    source: Mapped[str | None] = mapped_column(String(300))


class Job(Base, Timestamps):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_claim", "state", "run_after"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspace.id"), index=True)
    type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    state: Mapped[str] = mapped_column(String(10), default="pending")
    # pending | running | done | dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = _ws()
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Append-only. Never updated or deleted by application code."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str | None] = mapped_column(String(200))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchEvidence(Base, Timestamps):
    __tablename__ = "research_evidence"
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    finding: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(10))  # verified | inferred
    confidence: Mapped[str] = mapped_column(String(10), default="medium")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))


class Campaign(Base, Timestamps):
    __tablename__ = "campaign"
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), default="draft")  # draft|active|paused|done
    offer: Mapped[str] = mapped_column(Text, default="")
    objective: Mapped[str] = mapped_column(String(300), default="Book a short intro call")
    tone: Mapped[str] = mapped_column(String(100), default="friendly, concise, professional")
    sender_name: Mapped[str] = mapped_column(String(200), default="")
    sender_company: Mapped[str] = mapped_column(String(200), default="")
    physical_address: Mapped[str] = mapped_column(String(500), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    work_start: Mapped[int] = mapped_column(Integer, default=9)
    work_end: Mapped[int] = mapped_column(Integer, default=17)
    daily_limit: Mapped[int] = mapped_column(Integer, default=30)
    channels: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["email"])
    sequence: Mapped[list[Any]] = mapped_column(
        JSONB, default=lambda: [{"step": 0, "day": 0}, {"step": 1, "day": 3}, {"step": 2, "day": 7}])
    icp: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    thresholds: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    blocked_regions: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["GB", "DE", "FR", "IT", "ES", "NL", "IE", "CA"])
    channel_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CampaignLead(Base, Timestamps):
    __tablename__ = "campaign_lead"
    __table_args__ = (UniqueConstraint("campaign_id", "lead_id"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign.id"), index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id"), index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(20), default="queued")  # queued|active|stopped|completed
    stop_reason: Mapped[str | None] = mapped_column(String(50))
    icp_score: Mapped[int | None] = mapped_column(Integer)
    icp_class: Mapped[str | None] = mapped_column(String(20))
    icp_confidence: Mapped[int | None] = mapped_column(Integer)
    icp_breakdown: Mapped[list[Any]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))


class GeneratedMessage(Base, Timestamps):
    __tablename__ = "generated_message"
    __table_args__ = (Index("ix_gm_campaign_status", "campaign_id", "status"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign.id"))
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id"), index=True)
    channel: Mapped[str] = mapped_column(String(20))
    step: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    claims: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    quality: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="template")  # template | llm
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # draft | needs_review | approved | rejected | sent
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_hash: Mapped[str | None] = mapped_column(String(64))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChannelAccount(Base, Timestamps):
    __tablename__ = "channel_account"
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    provider: Mapped[str] = mapped_column(String(20))  # mock | smtp
    channel: Mapped[str] = mapped_column(String(20), default="email")
    name: Mapped[str] = mapped_column(String(200))
    from_email: Mapped[str] = mapped_column(String(320))
    credentials_enc: Mapped[str | None] = mapped_column(Text)  # Fernet token; never returned by API
    daily_limit: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="active")
    health: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sync_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))  # IMAP cursor: uidvalidity, last_uid, next_at


class Conversation(Base, Timestamps):
    __tablename__ = "conversation"
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id"), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("campaign.id"))
    channel: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(String(300))
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | closed
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Message(Base, Timestamps):
    __tablename__ = "message"
    __table_args__ = (
        Index("uq_message_idem", "idempotency_key", unique=True, postgresql_where=text("idempotency_key IS NOT NULL")),
        Index("ix_message_header", "workspace_id", "message_id_header"),
    )
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation.id"), index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id"), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    generated_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    direction: Mapped[str] = mapped_column(String(10))  # out | in
    channel: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="sent")  # sending|sent|failed|needs_manual_check|received
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(300))
    message_id_header: Mapped[str | None] = mapped_column(String(300))
    in_reply_to: Mapped[str | None] = mapped_column(String(300))
    peer: Mapped[str | None] = mapped_column(String(320))  # sender address of an inbound message
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    intent: Mapped[str | None] = mapped_column(String(30))
    intent_confidence: Mapped[int | None] = mapped_column(Integer)
    intent_source: Mapped[str | None] = mapped_column(String(20))  # rules | llm | human
    suggested_reply: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)


class ScheduledAction(Base, Timestamps):
    __tablename__ = "scheduled_action"
    __table_args__ = (
        UniqueConstraint("idempotency_key"),
        Index("ix_sa_due", "state", "run_at"),
    )
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id"), index=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign.id"), index=True)
    generated_message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("generated_message.id"))
    step: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(20))
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | claiming | sent | failed | cancelled | needs_manual_check
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    last_error: Mapped[str | None] = mapped_column(Text)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderEvent(Base, Timestamps):
    __tablename__ = "provider_event"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Opportunity(Base, Timestamps):
    __tablename__ = "opportunity"
    id: Mapped[uuid.UUID] = _id()
    workspace_id: Mapped[uuid.UUID] = _ws()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id"), index=True)
    stage: Mapped[str] = mapped_column(String(20), default="new")
    value: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIUsageRecord(Base):
    __tablename__ = "ai_usage_record"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    task: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
