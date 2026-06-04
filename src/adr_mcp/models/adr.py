"""Pydantic models for ADR lifecycle, tools and persistence boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ADRStatus(StrEnum):
    DRAFT = "DRAFT"
    ACCEPTED = "ACCEPTED"
    DEPRECATED = "DEPRECATED"


class ConflictType(StrEnum):
    CONTRADICTION = "CONTRADICTION"
    DEPENDENCY = "DEPENDENCY"
    OVERLAP = "OVERLAP"


class ConflictSeverity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AuditEventType(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    DEPRECATED = "DEPRECATED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    REINDEXED = "REINDEXED"


class ADRStructure(BaseModel):
    """Strict JSON object expected from the extraction prompt."""

    title: str = Field(min_length=1)
    context: str = Field(min_length=1)
    decision: str = Field(default="")
    options_considered: list[str] = Field(default_factory=list)
    consequences: str = Field(default="")
    tags: list[str] = Field(default_factory=list)
    supersedes: str | None = None

    @field_validator("tags", mode="after")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return sorted({tag.strip().lower() for tag in value if tag.strip()})


class ConflictResult(BaseModel):
    candidate_id: str
    type: ConflictType
    explanation: str
    severity: ConflictSeverity


class StepStatus(BaseModel):
    name: str
    ok: bool
    message: str | None = None


class AuditEvent(BaseModel):
    id: int | None = None
    adr_id: str
    event_type: AuditEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ADRRecord(BaseModel):
    id: str
    project_id: str
    title: str
    status: ADRStatus
    context: str
    decision: str
    consequences: str
    options_considered: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    supersedes: str | None = None
    created_at: str
    updated_at: str
    author: str | None = None
    embedding_model: str | None = None
    audit_log: list[AuditEvent] = Field(default_factory=list)
    supersession_chain: list[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class ADRResult(BaseModel):
    id: str
    title: str
    status: ADRStatus
    conflicts: list[ConflictResult] = Field(default_factory=list)
    steps: list[StepStatus] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class ADRSearchResult(BaseModel):
    id: str
    title: str
    score: float
    snippet: str
    tags: list[str]
    status: ADRStatus

    model_config = ConfigDict(use_enum_values=True)


class PaginatedADRList(BaseModel):
    items: list[ADRSearchResult]
    total: int
    page: int
    page_size: int


class SummaryResult(BaseModel):
    summary: str
    adr_count: int
    token_estimate: int
    hierarchical: bool = False


class ReindexResult(BaseModel):
    reindexed: int
    embedding_model: str
    failures: list[dict[str, str]] = Field(default_factory=list)


class CreateADRInput(BaseModel):
    raw_text: str = Field(min_length=1, description="Free-text decision, problem and context.")
    project_id: str = Field(default="default", min_length=1)
    author: str | None = None


class SearchDecisionsInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    filter_tags: list[str] | None = None
    status: ADRStatus | None = None


class CheckConflictsInput(BaseModel):
    adr_id: str = Field(min_length=1)


class GetADRInput(BaseModel):
    adr_id: str = Field(min_length=1)


class DeprecateADRInput(BaseModel):
    adr_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    superseded_by: str | None = None


class SummarizeProjectInput(BaseModel):
    project_id: str | None = None
    include_deprecated: bool = False


class ListADRsInput(BaseModel):
    project_id: str | None = None
    status: ADRStatus | None = None
    tags: list[str] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ReindexEmbeddingsInput(BaseModel):
    project_id: str | None = None
    batch_size: int = Field(default=10, ge=1, le=100)
    concurrency: int = Field(default=3, ge=1, le=10)
