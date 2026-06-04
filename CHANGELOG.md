# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to Semantic Versioning.

## [1.0.0] - 2026-06-04

### Added

- Initial ADR Manager MCP Server implementation.
- MCP tools: `create_adr`, `search_decisions`, `check_conflicts`, `get_adr`, `deprecate_adr`, `summarize_project`, `list_adrs`, and `reindex_embeddings`.
- SQLite persistence with append-only audit log triggers.
- Optional sqlite-vec initialization path with Python cosine fallback.
- AI service abstraction for Claude extraction, conflict reasoning and summarization.
- Mockable AI test suite with coverage target >= 80%.
- MCP registry manifest in `mcp.json`.
- Claude Desktop and MCP Inspector documentation.
