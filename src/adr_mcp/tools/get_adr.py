"""get_adr MCP tool handler."""

from __future__ import annotations

from typing import Any

from adr_mcp.models.adr import GetADRInput
from adr_mcp.models.errors import serialize_tool_error
from adr_mcp.services.adr_service import ADRService


async def get_adr_handler(service: ADRService, **kwargs: Any) -> dict[str, Any]:
    try:
        request = GetADRInput.model_validate(kwargs)
        result = await service.get_adr(request.adr_id)
        return result.model_dump(mode="json")
    except Exception as exc:
        return {"error": serialize_tool_error(exc)}
