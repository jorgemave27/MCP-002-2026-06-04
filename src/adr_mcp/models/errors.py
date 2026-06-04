"""Structured MCP-compatible error models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPErrorModel(BaseModel):
    """Error payload returned by tool handlers instead of raw exceptions."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable message for the MCP client.")
    details: dict[str, Any] = Field(default_factory=dict)


class ADRMCPError(Exception):
    """Application exception that can be safely serialized to MCP clients."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_model(self) -> MCPErrorModel:
        return MCPErrorModel(code=self.code, message=self.message, details=self.details)


def serialize_tool_error(exc: Exception) -> dict[str, Any]:
    """Convert known and unknown exceptions to the public error contract."""
    if isinstance(exc, ADRMCPError):
        return exc.to_model().model_dump()
    return MCPErrorModel(
        code="internal_error",
        message="Unexpected server error while executing MCP tool.",
        details={"exception_type": exc.__class__.__name__},
    ).model_dump()
