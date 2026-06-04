"""deprecate_adr MCP tool handler."""

from __future__ import annotations

from typing import Any

from adr_mcp.models.adr import DeprecateADRInput
from adr_mcp.models.errors import serialize_tool_error
from adr_mcp.services.adr_service import ADRService


async def deprecate_adr_handler(service: ADRService, **kwargs: Any) -> dict[str, Any]:
    try:
        request = DeprecateADRInput.model_validate(kwargs)
        result = await service.deprecate_adr(
            adr_id=request.adr_id,
            reason=request.reason,
            superseded_by=request.superseded_by,
        )
        return result.model_dump(mode="json")
    except Exception as exc:
        return {"error": serialize_tool_error(exc)}
