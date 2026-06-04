# MCP-002 Specification Implementation Matrix

This matrix maps the technical specification to repository artifacts.

| Spec area | Implementation |
|---|---|
| Python MCP server | `src/adr_mcp/server.py` using `FastMCP`. |
| Tool names in snake_case | `create_adr`, `search_decisions`, `check_conflicts`, `get_adr`, `deprecate_adr`, `summarize_project`, `list_adrs`, `reindex_embeddings`. |
| Pydantic validation | `src/adr_mcp/models/adr.py`; tool handlers validate with `model_validate`. |
| SQLite storage | `src/adr_mcp/storage/database.py` and `src/adr_mcp/storage/migrations/001_initial.sql`. |
| sqlite-vec vector support | Best-effort extension loading in `Database._try_enable_sqlite_vec`; JSON embedding fallback keeps tests deterministic. |
| Audit log append-only | SQL triggers `adr_audit_log_no_update` and `adr_audit_log_no_delete`. |
| AI structure extraction | `AIService.extract_structure`. |
| AI embeddings | `AIService.generate_embedding`, model from `ADR_EMBEDDING_MODEL`. |
| AI conflict reasoning | `AIService.reason_about_conflict`; concurrency controlled with semaphore(3) in `ADRService.check_conflicts`. |
| Semantic search score threshold | `Settings.adr_conflict_threshold`, default `0.72`; enforced in search and conflict candidate retrieval. |
| Partial failure isolation | `ADRService.create_adr` stores ADR even if extraction, embedding or conflict detection partially fail. |
| Deprecation lifecycle | `ADRService.deprecate_adr` blocks re-deprecation and deprecated replacement ADRs. |
| Token budget | `AIService.estimate_tokens` and hierarchical summary in `ADRService._hierarchical_summary`. |
| Re-indexing after embedding drift | `ADRService.reindex_embeddings` and MCP tool `reindex_embeddings`. |
| Structured MCP errors | `src/adr_mcp/models/errors.py` and all tool handlers. |
| Community readiness | `README.md`, `CHANGELOG.md`, `mcp.json`, package metadata, CI workflow. |
| Test coverage target | `pyproject.toml` config uses `--cov-fail-under=80`. |

## Notes

- The source specification requires local-first operation and no network calls except explicitly configured AI calls. The code follows this by isolating all AI calls in `AIService`.
- Tests use mocked AI and never call external APIs.
- The original confidential PDF is intentionally not committed into the repository. This repo includes a derived implementation matrix and source code instead.
