import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    email: str
    password: str


class LeadOut(ORM):
    id: uuid.UUID
    company_id: uuid.UUID | None
    first_name: str | None
    last_name: str | None
    title: str | None
    email: str | None
    email_norm: str | None
    phone_e164: str | None
    linkedin_url: str | None
    instagram_url: str | None
    source_url: str | None
    region: str | None
    status: str
    opted_out: bool
    possible_duplicate_of: uuid.UUID | None
    research_status: str
    icp_score: int | None
    icp_class: str | None
    icp_confidence: int | None
    custom: dict[str, Any]
    import_batch_id: uuid.UUID | None
    created_at: datetime


class LeadDetail(LeadOut):
    raw: dict[str, Any]
    lawful_basis: str | None
    company: dict[str, Any] | None = None
    timeline: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    icp_breakdown: list[dict[str, Any]] = []
    campaigns: list[dict[str, Any]] = []


class LeadPage(BaseModel):
    items: list[LeadOut]
    next_cursor: str | None


class LeadPatch(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    region: str | None = Field(default=None, min_length=2, max_length=2)
    lawful_basis: str | None = Field(default=None, max_length=500)
    status: str | None = None


class MappingIn(BaseModel):
    mapping: dict[str, str]
    default_region: str | None = Field(default=None, min_length=2, max_length=2)


class BatchOut(ORM):
    id: uuid.UUID
    filename: str
    status: str
    headers: list[str]
    mapping: dict[str, str]
    default_region: str | None
    total_rows: int
    next_row: int
    created_count: int
    duplicate_count: int
    invalid_count: int
    suppressed_count: int
    error: str | None
    created_at: datetime


class SuppressionIn(BaseModel):
    kind: str = Field(pattern="^(email|domain|phone)$")
    value: str
    reason: str = "manual"


class SuppressionOut(ORM):
    id: uuid.UUID
    kind: str
    value_norm: str
    reason: str
    source: str | None
    created_at: datetime


class JobOut(ORM):
    id: uuid.UUID
    type: str
    state: str
    attempts: int
    max_attempts: int
    run_after: datetime
    last_error: str | None
    payload: dict[str, Any]
    created_at: datetime
