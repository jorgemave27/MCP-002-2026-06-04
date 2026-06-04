"""summarize_project MCP tool handler."""

from __future__ import annotations

from typing import Any

from adr_mcp.models.adr import SummarizeProjectInput
from adr_mcp.models.errors import serialize_tool_error
from adr_mcp.services.adr_service import ADRService


async def summarize_project_handler(service: ADRService, **kwargs: Any) -> dict[str, Any]:
    try:
        request = SummarizeProjectInput.model_validate(kwargs)
        result = await service.summarize_project(
            project_id=request.project_id,
            include_deprecated=request.include_deprecated,
        )
        return result.model_dump(mode="json")
    except Exception as exc:
        return {"error": serialize_tool_error(exc)}
