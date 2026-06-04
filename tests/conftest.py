from __future__ import annotations

import pytest

from adr_mcp.config import Settings
from adr_mcp.models.adr import ADRRecord, ADRStructure, ConflictResult, ConflictSeverity, ConflictType
from adr_mcp.services.adr_service import ADRService
from adr_mcp.storage.database import Database


class MockAIService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.embedding_calls = 0

    async def extract_structure(self, raw_text: str) -> ADRStructure:
        if "FAIL_EXTRACTION" in raw_text:
            raise RuntimeError("forced extraction failure")
        lowered = raw_text.lower()
        title = "Architecture Decision"
        tags = ["architecture"]
        if "postgres" in lowered or "postgresql" in lowered:
            title = "Use PostgreSQL"
            tags = ["database", "postgresql"]
        elif "mongo" in lowered or "mongodb" in lowered:
            title = "Use MongoDB"
            tags = ["database", "mongodb"]
        elif "kafka" in lowered:
            title = "Use Kafka"
            tags = ["messaging", "kafka"]
        elif "redis" in lowered:
            title = "Use Redis"
            tags = ["cache", "redis"]
        return ADRStructure(
            title=title,
            context=raw_text,
            decision=raw_text,
            options_considered=["Option A", "Option B"],
            consequences="Documented trade-offs and operational consequences.",
            tags=tags,
            supersedes=None,
        )

    async def generate_embedding(self, text: str) -> list[float]:
        self.embedding_calls += 1
        lowered = text.lower()
        vector = [0.0] * 1536
        if any(word in lowered for word in ["database", "postgres", "postgresql", "mongo", "mongodb"]):
            vector[0] = 3.0
        if "postgres" in lowered or "postgresql" in lowered:
            vector[1] = 1.0
        if "mongo" in lowered or "mongodb" in lowered:
            vector[1] = -1.0
        if any(word in lowered for word in ["message", "event", "kafka"]):
            vector[2] = 3.0
        if any(word in lowered for word in ["cache", "redis"]):
            vector[3] = 3.0
        if not any(vector):
            vector[10] = 1.0
        return vector

    async def reason_about_conflict(
        self, source: ADRRecord, candidate: ADRRecord
    ) -> ConflictResult | None:
        joined = f"{source.decision} {candidate.decision}".lower()
        source_db = "postgres" in source.decision.lower() or "postgresql" in source.decision.lower()
        candidate_mongo = "mongo" in candidate.decision.lower() or "mongodb" in candidate.decision.lower()
        source_mongo = "mongo" in source.decision.lower() or "mongodb" in source.decision.lower()
        candidate_db = "postgres" in candidate.decision.lower() or "postgresql" in candidate.decision.lower()
        if (source_db and candidate_mongo) or (source_mongo and candidate_db):
            return ConflictResult(
                candidate_id=candidate.id,
                type=ConflictType.CONTRADICTION,
                explanation="Both ADRs choose incompatible primary databases for the same domain.",
                severity=ConflictSeverity.HIGH,
            )
        if "kafka" in joined and "outbox" in joined:
            return ConflictResult(
                candidate_id=candidate.id,
                type=ConflictType.DEPENDENCY,
                explanation="Kafka eventing depends on the outbox publishing decision.",
                severity=ConflictSeverity.MEDIUM,
            )
        return None

    async def summarize(self, records: list[ADRRecord]) -> str:
        titles = ", ".join(record.title for record in records)
        return f"# ADR Summary\n\nReviewed {len(records)} ADRs: {titles}."

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


@pytest.fixture
async def service(tmp_path) -> ADRService:
    settings = Settings(
        ANTHROPIC_API_KEY="test-key-not-used",
        ADR_DB_PATH=tmp_path / "adr.db",
        ADR_CONFLICT_THRESHOLD=0.72,
    )
    db = Database(settings.adr_db_path)
    await db.connect()
    ai = MockAIService(settings)
    service = ADRService(db=db, ai=ai, settings=settings)  # type: ignore[arg-type]
    yield service
    await db.close()
