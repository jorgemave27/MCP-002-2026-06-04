# Acceptance Checklist

## Functional

- [x] Tools exposed through MCP-compatible server entrypoint.
- [x] `create_adr` extracts structure, persists ADR and embedding when AI succeeds.
- [x] `create_adr` preserves raw text as `DRAFT` when extraction fails.
- [x] `search_decisions` uses cosine similarity and filters out scores below threshold.
- [x] `check_conflicts` separates retrieval from pairwise reasoning and uses semaphore(3).
- [x] `deprecate_adr` prevents re-deprecation.
- [x] `summarize_project` estimates tokens and supports hierarchical summarization.
- [x] `reindex_embeddings` regenerates embeddings in batches.

## Non-functional

- [x] Tool errors are structured as `{code, message, details}`.
- [x] AI calls have explicit 30s timeout via `httpx.AsyncClient`.
- [x] Audit log is append-only through SQL triggers.
- [x] AI service is mockable; tests do not call external APIs.
- [x] Test configuration enforces >= 80% coverage.
- [x] Cold-start path is lazy and minimal: settings, DB connection, schema validation.

## Community readiness

- [x] README includes installation instructions.
- [x] README includes Claude Desktop configuration.
- [x] README includes multiple examples.
- [x] `mcp.json` includes public tool definitions.
- [x] `CHANGELOG.md` follows Keep a Changelog structure.
