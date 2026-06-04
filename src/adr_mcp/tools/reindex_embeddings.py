"""reindex_embeddings MCP tool handler."""

from __future__ import annotations

from typing import Any

from adr_mcp.models.adr import ReindexEmbeddingsInput
from adr_mcp.models.errors import serialize_tool_error
from adr_mcp.services.adr_service import ADRService


async def reindex_embeddings_handler(service: ADRService, **kwargs: Any) -> dict[str, Any]:
    try:
        request = ReindexEmbeddingsInput.model_validate(kwargs)
        result = await service.reindex_embeddings(
            project_id=request.project_id,
            batch_size=request.batch_size,
            concurrency=request.concurrency,
        )
        return result.model_dump(mode="json")
    except Exception as exc:
        return {"error": serialize_tool_error(exc)}
