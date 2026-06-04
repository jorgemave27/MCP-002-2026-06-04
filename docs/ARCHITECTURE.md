# Architecture

## Layers

```text
Client: Claude Desktop / Cursor / MCP Inspector
    |
MCP transport: src/adr_mcp/server.py
    |
Tool handlers: src/adr_mcp/tools/*.py
    |
Services: ADRService + AIService
    |
Storage: SQLite + adr_embeddings + optional vec_adrs
```

## create_adr flow

```text
create_adr(raw_text)
  -> validate CreateADRInput
  -> AIService.extract_structure(raw_text)
  -> AIService.generate_embedding(structured content)
  -> ADRService persists ADR + embedding
  -> ADRService.check_conflicts(id)
      -> vector retrieval
      -> pairwise LLM reasoning with semaphore(3)
  -> return ADRResult(id, title, status, conflicts, steps)
```

## Failure isolation

`create_adr` intentionally does not wrap the entire chain in a single transaction. Extraction,
embedding and conflict detection each have their own error boundary:

- Extraction failure: raw text is saved as `DRAFT`.
- Embedding failure: structured ADR is saved as `DRAFT` without embedding.
- Conflict detection failure: ADR and embedding remain persisted; the response includes a failed step.

## Vector search strategy

The implementation persists embeddings in a JSON fallback table and attempts to create the
`vec_adrs` virtual table when sqlite-vec is available. The service uses cosine similarity and a
minimum score threshold of `0.72` by default.

## Audit guarantees

The audit log is append-only at SQL level through triggers. Application code does not expose
update or delete operations for audit events.
