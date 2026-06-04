"""AI boundary for structure extraction, embeddings, conflict reasoning and summaries."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from adr_mcp.config import Settings
from adr_mcp.models.adr import ADRRecord, ADRStructure, ConflictResult, ConflictSeverity, ConflictType
from adr_mcp.models.errors import ADRMCPError

LOGGER = logging.getLogger(__name__)


class AIService:
    """Async, mockable AI service.

    Production calls use Anthropic-style message endpoints for extraction, conflict reasoning
    and summaries. Embeddings are kept behind the same abstraction so tests and local
    development can inject deterministic vectors without hitting the network.
    """

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> "AIService":
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.settings.adr_ai_timeout_seconds)
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.settings.adr_ai_timeout_seconds)
        return self._client

    async def extract_structure(self, raw_text: str) -> ADRStructure:
        prompt = (
            "You are extracting an Architecture Decision Record. Return strict JSON only "
            "with keys: title, context, decision, options_considered, consequences, tags, "
            "supersedes. No markdown. Raw text:\n\n"
            f"{raw_text}"
        )
        data = await self._call_claude_json(prompt, max_tokens=1500)
        try:
            return ADRStructure.model_validate(data)
        except ValidationError as exc:
            raise ADRMCPError(
                "ai_extraction_schema_error",
                "Claude returned JSON that does not match the ADR extraction schema.",
                {"errors": exc.errors()},
            ) from exc

    async def generate_embedding(self, text: str) -> list[float]:
        """Generate a 1536-dimension embedding.

        The PDF specifies `voyage-3` as the default embedding model. Implementations often
        proxy this through an external embedding provider; this method keeps the public contract
        while remaining mockable. If a provider endpoint is not available, it raises a structured
        error rather than silently returning fake production data.
        """
        api_key = self._require_api_key()
        url = "https://api.anthropic.com/v1/embeddings"
        payload = {"model": self.settings.adr_embedding_model, "input": text}
        headers = self._headers(api_key)
        try:
            response = await self.client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            embedding = body.get("embedding") or body.get("data", [{}])[0].get("embedding")
            if not isinstance(embedding, list):
                raise ValueError("embedding field missing")
            return [float(value) for value in embedding]
        except Exception as exc:
            raise ADRMCPError(
                "ai_embedding_error",
                "Failed to generate embedding for ADR content.",
                {"model": self.settings.adr_embedding_model, "reason": str(exc)},
            ) from exc

    async def reason_about_conflict(self, source: ADRRecord, candidate: ADRRecord) -> ConflictResult | None:
        prompt = (
            "Compare two Architecture Decision Records. Return strict JSON only. "
            "If there is no relevant relationship, return {\"conflict\": false}. "
            "If there is a relationship, return conflict=true, type as one of "
            "CONTRADICTION, DEPENDENCY, OVERLAP, severity as HIGH, MEDIUM, LOW, "
            "and a short explanation.\n\n"
            f"ADR A:\n{self._record_for_prompt(source)}\n\n"
            f"ADR B:\n{self._record_for_prompt(candidate)}"
        )
        data = await self._call_claude_json(prompt, max_tokens=700)
        if not data.get("conflict"):
            return None
        try:
            return ConflictResult(
                candidate_id=candidate.id,
                type=ConflictType(str(data["type"])),
                explanation=str(data["explanation"]),
                severity=ConflictSeverity(str(data["severity"])),
            )
        except Exception as exc:
            raise ADRMCPError(
                "ai_conflict_schema_error",
                "Claude returned invalid conflict reasoning JSON.",
                {"payload": data},
            ) from exc

    async def summarize(self, records: list[ADRRecord]) -> str:
        prompt = (
            "Create a concise onboarding markdown narrative from these ADRs. "
            "Do not invent decisions. Group by architectural theme and call out deprecated "
            "decisions explicitly.\n\n"
            + "\n\n---\n\n".join(self._record_for_prompt(record) for record in records)
        )
        data = await self._call_claude_json(
            prompt + "\n\nReturn JSON only: {\"summary\": \"markdown text\"}",
            max_tokens=2500,
        )
        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ADRMCPError(
                "ai_summary_schema_error",
                "Claude summary response did not include a non-empty summary field.",
                {"payload": data},
            )
        return summary

    def estimate_tokens(self, text: str) -> int:
        try:  # pragma: no cover - optional dependency path.
            import tiktoken

            encoder = tiktoken.get_encoding("cl100k_base")
            return len(encoder.encode(text))
        except Exception:
            return max(1, len(text) // 4)

    async def _call_claude_json(self, prompt: str, max_tokens: int) -> dict[str, Any]:
        api_key = self._require_api_key()
        headers = self._headers(api_key)
        payload = {
            "model": self.settings.adr_llm_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            response = await self.client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            content = body.get("content", [])
            text = ""
            if content and isinstance(content, list):
                text = str(content[0].get("text", ""))
            elif isinstance(body.get("completion"), str):
                text = body["completion"]
            return json.loads(self._strip_json_fence(text))
        except ADRMCPError:
            raise
        except Exception as exc:
            raise ADRMCPError(
                "ai_call_error",
                "Failed to complete Claude JSON call.",
                {"model": self.settings.adr_llm_model, "reason": str(exc)},
            ) from exc

    def _require_api_key(self) -> str:
        try:
            return self.settings.require_anthropic_api_key()
        except ValueError as exc:
            raise ADRMCPError("missing_api_key", str(exc), {}) from exc

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.removeprefix("```json").removeprefix("```").removesuffix("```")
        return stripped.strip()

    @staticmethod
    def _record_for_prompt(record: ADRRecord) -> str:
        return (
            f"ID: {record.id}\nTitle: {record.title}\nStatus: {record.status}\n"
            f"Context: {record.context}\nDecision: {record.decision}\n"
            f"Options: {record.options_considered}\nConsequences: {record.consequences}\n"
            f"Tags: {record.tags}"
        )


class DeterministicEmbeddingMixin:
    """Utility mixin useful for local demos and tests."""

    @staticmethod
    def deterministic_embedding(text: str, dimensions: int = 1536) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        while len(values) < dimensions:
            for byte in digest:
                values.append((byte / 255.0) * 2.0 - 1.0)
                if len(values) == dimensions:
                    break
            digest = hashlib.sha256(digest).digest()
        return values
