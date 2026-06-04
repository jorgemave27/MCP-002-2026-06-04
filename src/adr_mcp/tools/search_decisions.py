"""search_decisions MCP tool handler."""

from __future__ import annotations

from typing import Any

from adr_mcp.models.adr import SearchDecisionsInput
from adr_mcp.models.errors import serialize_tool_error
from adr_mcp.services.adr_service import ADRService


async def search_decisions_handler(service: ADRService, **kwargs: Any) -> dict[str, Any]:
    try:
        request = SearchDecisionsInput.model_validate(kwargs)
        results = await service.search_decisions(
            query=request.query,
            top_k=request.top_k,
            filter_tags=request.filter_tags,
            status=request.status,
        )
        return {"results": [item.model_dump(mode="json") for item in results]}
    except Exception as exc:
        return {"error": serialize_tool_error(exc)}
