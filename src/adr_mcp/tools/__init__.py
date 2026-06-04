"""MCP tool handler modules."""

from adr_mcp.tools.check_conflicts import check_conflicts_handler
from adr_mcp.tools.create_adr import create_adr_handler
from adr_mcp.tools.deprecate_adr import deprecate_adr_handler
from adr_mcp.tools.get_adr import get_adr_handler
from adr_mcp.tools.list_adrs import list_adrs_handler
from adr_mcp.tools.reindex_embeddings import reindex_embeddings_handler
from adr_mcp.tools.search_decisions import search_decisions_handler
from adr_mcp.tools.summarize_project import summarize_project_handler

__all__ = [
    "check_conflicts_handler",
    "create_adr_handler",
    "deprecate_adr_handler",
    "get_adr_handler",
    "list_adrs_handler",
    "reindex_embeddings_handler",
    "search_decisions_handler",
    "summarize_project_handler",
]
