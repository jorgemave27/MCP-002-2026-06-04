from __future__ import annotations

import json

import pytest

from adr_mcp.config import Settings
from adr_mcp.models.adr import ADRRecord, ADRStatus, ConflictSeverity, ConflictType
from adr_mcp.models.errors import ADRMCPError
from adr_mcp.services.ai_service import AIService, DeterministicEmbeddingMixin


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.calls: list[dict] = []
        self.closed = False

    async def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(self.payloads.pop(0))

    async def aclose(self) -> None:
        self.closed = True


def make_settings(api_key: str | None = "test-key") -> Settings:
    return Settings(ANTHROPIC_API_KEY=api_key)


def make_record(record_id: str = "adr-1", title: str = "Use PostgreSQL") -> ADRRecord:
    return ADRRecord(
        id=record_id,
        project_id="core",
        title=title,
        status=ADRStatus.ACCEPTED,
        context="We need transactional consistency.",
        decision="Use PostgreSQL.",
        consequences="Strong consistency with relational constraints.",
        options_considered=["MongoDB", "PostgreSQL"],
        tags=["database"],
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_extract_structure_parses_claude_json_response() -> None:
    adr_json = {
        "title": "Use PostgreSQL",
        "context": "Billing needs ACID transactions.",
        "decision": "Use PostgreSQL.",
        "options_considered": ["MongoDB", "PostgreSQL"],
        "consequences": "Better consistency.",
        "tags": ["Database", "PostgreSQL"],
        "supersedes": None,
    }
    client = FakeClient(
        [
            {
                "content": [
                    {
                        "text": "```json\n" + json.dumps(adr_json) + "\n```",
                    }
                ]
            }
        ]
    )
    service = AIService(make_settings(), client=client)  # type: ignore[arg-type]

    result = await service.extract_structure("We decided to use PostgreSQL.")

    assert result.title == "Use PostgreSQL"
    assert result.tags == ["database", "postgresql"]
    assert client.calls[0]["url"].endswith("/v1/messages")


@pytest.mark.asyncio
async def test_generate_embedding_accepts_embedding_payload() -> None:
    client = FakeClient([{"embedding": [0, 1, "2.5"]}])
    service = AIService(make_settings(), client=client)  # type: ignore[arg-type]

    embedding = await service.generate_embedding("database decision")

    assert embedding == [0.0, 1.0, 2.5]
    assert client.calls[0]["url"].endswith("/v1/embeddings")


@pytest.mark.asyncio
async def test_generate_embedding_accepts_data_payload() -> None:
    client = FakeClient([{"data": [{"embedding": [1, 2, 3]}]}])
    service = AIService(make_settings(), client=client)  # type: ignore[arg-type]

    embedding = await service.generate_embedding("database decision")

    assert embedding == [1.0, 2.0, 3.0]


@pytest.mark.asyncio
async def test_missing_api_key_returns_structured_error() -> None:
    service = AIService(make_settings(api_key=None), client=FakeClient([]))  # type: ignore[arg-type]

    with pytest.raises(ADRMCPError) as exc_info:
        await service.generate_embedding("text")

    assert exc_info.value.code == "missing_api_key"


@pytest.mark.asyncio
async def test_reason_about_conflict_returns_conflict_result() -> None:
    payload = {
        "content": [
            {
                "text": json.dumps(
                    {
                        "conflict": True,
                        "type": "OVERLAP",
                        "explanation": "Both ADRs discuss database selection.",
                        "severity": "LOW",
                    }
                )
            }
        ]
    }
    client = FakeClient([payload])
    service = AIService(make_settings(), client=client)  # type: ignore[arg-type]

    result = await service.reason_about_conflict(make_record("a"), make_record("b", "Use MongoDB"))

    assert result is not None
    assert result.type == ConflictType.OVERLAP
    assert result.severity == ConflictSeverity.LOW
    assert result.candidate_id == "b"


@pytest.mark.asyncio
async def test_reason_about_conflict_returns_none_when_no_conflict() -> None:
    client = FakeClient([{"content": [{"text": json.dumps({"conflict": False})}]}])
    service = AIService(make_settings(), client=client)  # type: ignore[arg-type]

    result = await service.reason_about_conflict(make_record("a"), make_record("b"))

    assert result is None


@pytest.mark.asyncio
async def test_summarize_returns_markdown_summary() -> None:
    client = FakeClient([{"content": [{"text": json.dumps({"summary": "# Summary\n\nADR overview."})}]}])
    service = AIService(make_settings(), client=client)  # type: ignore[arg-type]

    summary = await service.summarize([make_record()])

    assert summary.startswith("# Summary")


@pytest.mark.asyncio
async def test_context_manager_closes_owned_client() -> None:
    service = AIService(make_settings())

    async with service as active:
        assert active.client is not None

    assert service._client is None


def test_estimate_tokens_and_deterministic_embedding() -> None:
    service = AIService(make_settings(), client=FakeClient([]))  # type: ignore[arg-type]

    assert service.estimate_tokens("hello world") >= 1

    embedding = DeterministicEmbeddingMixin.deterministic_embedding("hello", dimensions=8)

    assert len(embedding) == 8
    assert all(isinstance(value, float) for value in embedding)
