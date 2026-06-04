"""list_adrs MCP tool handler."""

from __future__ import annotations

from typing import Any

from adr_mcp.models.adr import ListADRsInput
from adr_mcp.models.errors import serialize_tool_error
from adr_mcp.services.adr_service import ADRService


async def list_adrs_handler(service: ADRService, **kwargs: Any) -> dict[str, Any]:
    try:
        request = ListADRsInput.model_validate(kwargs)
        result = await service.list_adrs(
            project_id=request.project_id,
            status=request.status,
            tags=request.tags,
            page=request.page,
            page_size=request.page_size,
        )
        return result.model_dump(mode="json")
    except Exception as exc:
        return {"error": serialize_tool_error(exc)}
