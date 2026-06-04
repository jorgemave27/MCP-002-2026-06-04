"""check_conflicts MCP tool handler."""

from __future__ import annotations

from typing import Any

from adr_mcp.models.adr import CheckConflictsInput
from adr_mcp.models.errors import serialize_tool_error
from adr_mcp.services.adr_service import ADRService


async def check_conflicts_handler(service: ADRService, **kwargs: Any) -> dict[str, Any]:
    try:
        request = CheckConflictsInput.model_validate(kwargs)
        results = await service.check_conflicts(request.adr_id)
        return {"conflicts": [item.model_dump(mode="json") for item in results]}
    except Exception as exc:
        return {"error": serialize_tool_error(exc)}
