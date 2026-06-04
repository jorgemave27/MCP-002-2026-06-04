"""MCP server entrypoint."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from adr_mcp.config import get_settings
from adr_mcp.services.adr_service import ADRService
from adr_mcp.services.ai_service import AIService
from adr_mcp.storage.database import Database
from adr_mcp.tools import (
    check_conflicts_handler,
    create_adr_handler,
    deprecate_adr_handler,
    get_adr_handler,
    list_adrs_handler,
    reindex_embeddings_handler,
    search_decisions_handler,
    summarize_project_handler,
)

mcp = FastMCP("adr-mcp-server")
_service: ADRService | None = None
_service_lock = asyncio.Lock()


async def get_service() -> ADRService:
    """Lazy service factory used by all MCP tools."""
    global _service
    if _service is not None:
        return _service
    async with _service_lock:
        if _service is not None:
            return _service
        settings = get_settings()
        logging.basicConfig(level=settings.adr_log_level)
        db = Database(settings.adr_db_path)
        await db.connect()
        ai = AIService(settings)
        _service = ADRService(db=db, ai=ai, settings=settings)
        return _service


@mcp.tool()
async def create_adr(raw_text: str, project_id: str = "default", author: str | None = None) -> dict[str, Any]:
    """Create an ADR from free text and run semantic conflict detection."""
    return await create_adr_handler(
        await get_service(), raw_text=raw_text, project_id=project_id, author=author
    )


@mcp.tool()
async def search_decisions(
    query: str,
    top_k: int = 5,
    filter_tags: list[str] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Search ADRs semantically using cosine similarity with optional filters."""
    return await search_decisions_handler(
        await get_service(), query=query, top_k=top_k, filter_tags=filter_tags, status=status
    )


@mcp.tool()
async def check_conflicts(adr_id: str) -> dict[str, Any]:
    """Check one ADR against the corpus for contradictions, dependencies and overlaps."""
    return await check_conflicts_handler(await get_service(), adr_id=adr_id)


@mcp.tool()
async def get_adr(adr_id: str) -> dict[str, Any]:
    """Read a full ADR including audit log and supersession chain."""
    return await get_adr_handler(await get_service(), adr_id=adr_id)


@mcp.tool()
async def deprecate_adr(
    adr_id: str,
    reason: str,
    superseded_by: str | None = None,
) -> dict[str, Any]:
    """Deprecate an ADR and optionally link the replacement ADR."""
    return await deprecate_adr_handler(
        await get_service(), adr_id=adr_id, reason=reason, superseded_by=superseded_by
    )


@mcp.tool()
async def summarize_project(
    project_id: str | None = None,
    include_deprecated: bool = False,
) -> dict[str, Any]:
    """Summarize ADR history as an onboarding narrative."""
    return await summarize_project_handler(
        await get_service(), project_id=project_id, include_deprecated=include_deprecated
    )


@mcp.tool()
async def list_adrs(
    project_id: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List ADR summaries with optional filters and SQL pagination."""
    return await list_adrs_handler(
        await get_service(), project_id=project_id, status=status, tags=tags, page=page, page_size=page_size
    )


@mcp.tool()
async def reindex_embeddings(
    project_id: str | None = None,
    batch_size: int = 10,
    concurrency: int = 3,
) -> dict[str, Any]:
    """Regenerate stored embeddings after changing the configured embedding model."""
    return await reindex_embeddings_handler(
        await get_service(), project_id=project_id, batch_size=batch_size, concurrency=concurrency
    )


def main() -> None:
    """Console script entrypoint."""
    mcp.run()


if __name__ == "__main__":
    main()
