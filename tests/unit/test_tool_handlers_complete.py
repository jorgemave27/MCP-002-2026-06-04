from __future__ import annotations

import pytest

from adr_mcp.tools.check_conflicts import check_conflicts_handler
from adr_mcp.tools.deprecate_adr import deprecate_adr_handler
from adr_mcp.tools.list_adrs import list_adrs_handler
from adr_mcp.tools.reindex_embeddings import reindex_embeddings_handler
from adr_mcp.tools.search_decisions import search_decisions_handler
from adr_mcp.tools.summarize_project import summarize_project_handler


@pytest.mark.asyncio
async def test_remaining_tool_handlers_success(service) -> None:
    first = await service.create_adr("We chose PostgreSQL as the primary database.", project_id="core")
    second = await service.create_adr("We chose MongoDB as the primary database.", project_id="core")

    search_response = await search_decisions_handler(
        service,
        query="database choice",
        top_k=5,
        filter_tags=["database"],
        status="ACCEPTED",
    )
    assert "results" in search_response
    assert len(search_response["results"]) >= 1

    conflicts_response = await check_conflicts_handler(service, adr_id=second.id)
    assert "conflicts" in conflicts_response

    list_response = await list_adrs_handler(service, project_id="core", page=1, page_size=10)
    assert list_response["total"] == 2

    summary_response = await summarize_project_handler(service, project_id="core")
    assert summary_response["adr_count"] == 2
    assert summary_response["summary"].startswith("# ADR Summary")

    reindex_response = await reindex_embeddings_handler(
        service,
        project_id="core",
        batch_size=1,
        concurrency=1,
    )
    assert reindex_response["reindexed"] == 2

    deprecate_response = await deprecate_adr_handler(
        service,
        adr_id=first.id,
        reason="MongoDB ADR replaces this decision.",
        superseded_by=second.id,
    )
    assert deprecate_response["status"] == "DEPRECATED"


@pytest.mark.asyncio
async def test_tool_handlers_validation_errors_are_serialized(service) -> None:
    response = await search_decisions_handler(service, query="", top_k=0)

    assert "error" in response
    assert response["error"]["code"] == "internal_error"
