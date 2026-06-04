from __future__ import annotations

import pytest

from adr_mcp.models.adr import ADRStatus, AuditEventType
from adr_mcp.models.errors import ADRMCPError


@pytest.mark.asyncio
async def test_create_adr_persists_accepted_with_audit_and_embedding(service) -> None:
    result = await service.create_adr(
        "We decided to use PostgreSQL for billing database transactions.",
        project_id="billing",
        author="team",
    )

    assert result.status == ADRStatus.ACCEPTED
    assert result.title == "Use PostgreSQL"

    record = await service.get_adr(result.id)
    assert record.project_id == "billing"
    assert record.audit_log[0].event_type == AuditEventType.CREATED

    embedding = await service._get_embedding(result.id)
    assert embedding is not None
    assert len(embedding) == 1536


@pytest.mark.asyncio
async def test_create_adr_saves_draft_when_extraction_fails(service) -> None:
    result = await service.create_adr("FAIL_EXTRACTION raw decision text", project_id="core")

    assert result.status == ADRStatus.DRAFT
    assert result.steps[0].ok is False
    record = await service.get_adr(result.id)
    assert record.context == "FAIL_EXTRACTION raw decision text"
    assert await service._get_embedding(result.id) is None


@pytest.mark.asyncio
async def test_search_decisions_filters_by_semantic_score_and_tags(service) -> None:
    await service.create_adr("We chose PostgreSQL for relational database workloads.", project_id="core")
    await service.create_adr("We chose Redis for caching hot keys.", project_id="core")

    results = await service.search_decisions(
        "database choice",
        top_k=5,
        filter_tags=["database"],
        status=ADRStatus.ACCEPTED,
    )

    assert len(results) == 1
    assert results[0].title == "Use PostgreSQL"
    assert results[0].score >= 0.72


@pytest.mark.asyncio
async def test_check_conflicts_detects_database_contradiction(service) -> None:
    first = await service.create_adr("We chose PostgreSQL as the primary database.", project_id="core")
    second = await service.create_adr("We chose MongoDB as the primary database.", project_id="core")

    conflicts = await service.check_conflicts(second.id)

    assert conflicts
    assert conflicts[0].candidate_id == first.id
    assert conflicts[0].type == "CONTRADICTION"


@pytest.mark.asyncio
async def test_deprecate_adr_and_prevent_redeprecation(service) -> None:
    old = await service.create_adr("We chose PostgreSQL as the primary database.", project_id="core")
    new = await service.create_adr("We chose MongoDB as the primary database.", project_id="core")

    deprecated = await service.deprecate_adr(old.id, "New decision supersedes it.", new.id)

    assert deprecated.status == ADRStatus.DEPRECATED
    assert deprecated.supersedes == new.id

    with pytest.raises(ADRMCPError, match="already DEPRECATED"):
        await service.deprecate_adr(old.id, "second attempt")


@pytest.mark.asyncio
async def test_list_adrs_paginates(service) -> None:
    await service.create_adr("We chose PostgreSQL for billing.", project_id="core")
    await service.create_adr("We chose Kafka for events.", project_id="core")

    page = await service.list_adrs(project_id="core", page=1, page_size=1)

    assert page.total == 2
    assert len(page.items) == 1
    assert page.page == 1


@pytest.mark.asyncio
async def test_summarize_project(service) -> None:
    await service.create_adr("We chose PostgreSQL for billing.", project_id="core")

    result = await service.summarize_project(project_id="core")

    assert result.adr_count == 1
    assert result.summary.startswith("# ADR Summary")


@pytest.mark.asyncio
async def test_reindex_embeddings(service) -> None:
    await service.create_adr("We chose PostgreSQL for billing.", project_id="core")
    result = await service.reindex_embeddings(project_id="core", batch_size=1, concurrency=1)

    assert result.reindexed == 1
    assert result.embedding_model == "voyage-3"
    assert not result.failures
