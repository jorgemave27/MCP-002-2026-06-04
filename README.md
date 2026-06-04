# ADR Manager MCP Server

`adr-mcp-server` is a Python MCP server that turns a local Architecture Decision Record repository into a living knowledge layer for AI-assisted development. It stores ADRs in SQLite, generates embeddings for semantic search, detects possible conflicts with LLM reasoning, and exposes a tool interface usable from Claude Desktop, Cursor, MCP Inspector, or custom agents.

This repository was prepared as **MCP-002-2026-06-04**.

## What it implements

The server exposes the required MCP tools:

| Tool | Purpose |
|---|---|
| `create_adr` | Create an ADR from free text, extract structure with AI, persist the ADR and embedding, then check conflicts. |
| `search_decisions` | Semantic ADR search with optional tag and status filters. |
| `check_conflicts` | Compare one ADR against similar ADRs and classify contradictions, dependencies or overlaps. |
| `get_adr` | Read a complete ADR, including audit history and supersession chain. |
| `deprecate_adr` | Mark an ADR as deprecated and optionally link the replacement ADR. |
| `summarize_project` | Generate an onboarding-style project summary from ADR history. |
| `list_adrs` | Paginated ADR listing with filters. |
| `reindex_embeddings` | Regenerate embeddings when the configured embedding model changes. |

## Architecture

```text
MCP Client
  -> MCP transport / tool router
  -> Pydantic input validation
  -> ADRService / AIService
  -> SQLite + optional sqlite-vec acceleration
```

The code follows four strict layers:

1. **Transport:** MCP SDK via `FastMCP` in `src/adr_mcp/server.py`.
2. **Tool router:** Thin tool handlers under `src/adr_mcp/tools/`.
3. **Services:** `ADRService` handles lifecycle, CRUD, search and audit; `AIService` handles Claude calls.
4. **Storage:** `Database` manages SQLite, migrations, locking and optional `sqlite-vec` initialization.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create a local environment file:

```bash
cp .env.example .env
```

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

> The server stores local data in `~/.adr-mcp/adr.db` unless `ADR_DB_PATH` is provided.

## Run with MCP Inspector

```bash
npx @modelcontextprotocol/inspector adr-mcp-server
```

## Claude Desktop configuration

Add this block to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "adr-manager": {
      "command": "adr-mcp-server",
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-REPLACE_ME",
        "ADR_DB_PATH": "/absolute/path/to/adr.db"
      }
    }
  }
}
```

## Usage examples

### 1. Create an ADR from free text

```json
{
  "tool": "create_adr",
  "arguments": {
    "raw_text": "We decided to use PostgreSQL for transactional data because we need relational integrity, joins and ACID semantics. We considered MongoDB but rejected it for this service.",
    "project_id": "billing-platform",
    "author": "platform-team"
  }
}
```

### 2. Search previous decisions semantically

```json
{
  "tool": "search_decisions",
  "arguments": {
    "query": "database choice for transactional workloads",
    "top_k": 5,
    "filter_tags": ["database"],
    "status": "ACCEPTED"
  }
}
```

### 3. Deprecate an ADR

```json
{
  "tool": "deprecate_adr",
  "arguments": {
    "adr_id": "ADR_UUID",
    "reason": "Replaced by the event-driven architecture decision.",
    "superseded_by": "NEW_ADR_UUID"
  }
}
```

## Testing

```bash
pytest
```

The suite is designed to run with mocked AI responses only. It should never call the Anthropic API during tests.

## Packaging

```bash
python -m build
pip install dist/adr_mcp_server-1.0.0-py3-none-any.whl
```

## Operational notes

- Non-AI tools are pure SQLite reads/writes and avoid network calls.
- All tool errors are returned as structured MCP-compatible error dictionaries.
- The audit log is append-only and protected by SQL triggers.
- Conflict detection uses vector retrieval first and LLM pairwise reasoning second.
- `summarize_project` estimates token budget and switches to hierarchical summarization when needed.
