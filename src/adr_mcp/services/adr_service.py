"""Business logic for ADR lifecycle, search, conflict detection and summaries."""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from adr_mcp.config import Settings
from adr_mcp.models.adr import (
    ADRRecord,
    ADRResult,
    ADRSearchResult,
    ADRStatus,
    ADRStructure,
    AuditEvent,
    AuditEventType,
    ConflictResult,
    ListADRsInput,
    PaginatedADRList,
    ReindexResult,
    StepStatus,
    SummaryResult,
)
from adr_mcp.models.errors import ADRMCPError
from adr_mcp.services.ai_service import AIService
from adr_mcp.storage.database import Database


class ADRService:
    """Core service independent from MCP internals."""

    def __init__(self, db: Database, ai: AIService, settings: Settings) -> None:
        self.db = db
        self.ai = ai
        self.settings = settings

    async def create_adr(self, raw_text: str, project_id: str = "default", author: str | None = None) -> ADRResult:
        steps: list[StepStatus] = []
        conflicts: list[ConflictResult] = []
        status = ADRStatus.ACCEPTED
        embedding: list[float] | None = None

        try:
            structure = await self.ai.extract_structure(raw_text)
            steps.append(StepStatus(name="extract_structure", ok=True))
        except Exception as exc:
            structure = self._draft_structure(raw_text)
            status = ADRStatus.DRAFT
            steps.append(
                StepStatus(
                    name="extract_structure",
                    ok=False,
                    message=f"ADR saved as DRAFT because extraction failed: {exc}",
                )
            )

        if status is ADRStatus.ACCEPTED:
            try:
                embedding = await self.ai.generate_embedding(self._structure_text(structure))
                steps.append(StepStatus(name="generate_embedding", ok=True))
            except Exception as exc:
                status = ADRStatus.DRAFT
                steps.append(
                    StepStatus(
                        name="generate_embedding",
                        ok=False,
                        message=f"ADR saved as DRAFT because embedding failed: {exc}",
                    )
                )

        record = await self._insert_adr(
            project_id=project_id,
            structure=structure,
            status=status,
            author=author,
            embedding_model=self.settings.adr_embedding_model if embedding else None,
        )
        await self._append_audit(
            record.id,
            AuditEventType.CREATED,
            {"status": status.value, "source": "create_adr"},
        )

        if embedding:
            await self._upsert_embedding(record.id, embedding, self.settings.adr_embedding_model)
            try:
                conflicts = await self.check_conflicts(record.id)
                steps.append(StepStatus(name="check_conflicts", ok=True))
            except Exception as exc:
                steps.append(
                    StepStatus(
                        name="check_conflicts",
                        ok=False,
                        message=f"ADR persisted, but conflict detection failed: {exc}",
                    )
                )

        return ADRResult(id=record.id, title=record.title, status=status, conflicts=conflicts, steps=steps)

    async def search_decisions(
        self,
        query: str,
        top_k: int = 5,
        filter_tags: list[str] | None = None,
        status: ADRStatus | None = None,
    ) -> list[ADRSearchResult]:
        query_embedding = await self.ai.generate_embedding(query)
        records = await self._get_records_for_search(status=status, tags=filter_tags)
        embeddings = await self._get_all_embeddings()

        scored: list[ADRSearchResult] = []
        for record in records:
            embedding = embeddings.get(record.id)
            if embedding is None:
                continue
            score = self._cosine_similarity(query_embedding, embedding)
            if score < self.settings.adr_conflict_threshold:
                continue
            scored.append(
                ADRSearchResult(
                    id=record.id,
                    title=record.title,
                    score=round(score, 6),
                    snippet=self._snippet(record),
                    tags=record.tags,
                    status=record.status,
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]

    async def check_conflicts(self, adr_id: str) -> list[ConflictResult]:
        source = await self.get_adr(adr_id)
        source_text = self._record_text(source)
        source_embedding = await self._get_embedding(adr_id)
        if source_embedding is None:
            source_embedding = await self.ai.generate_embedding(source_text)
            await self._upsert_embedding(adr_id, source_embedding, self.settings.adr_embedding_model)

        candidates = await self._similar_candidates(source, source_embedding)
        semaphore = asyncio.Semaphore(3)

        async def compare(candidate: ADRRecord) -> ConflictResult | None:
            async with semaphore:
                return await self.ai.reason_about_conflict(source, candidate)

        results = await asyncio.gather(*(compare(candidate) for candidate in candidates), return_exceptions=True)
        conflicts: list[ConflictResult] = []
        for result in results:
            if isinstance(result, ConflictResult):
                conflicts.append(result)
                await self._append_audit(
                    adr_id,
                    AuditEventType.CONFLICT_DETECTED,
                    result.model_dump(mode="json"),
                )
            elif isinstance(result, Exception):
                # Pairwise failures must not make the whole tool fail.
                await self._append_audit(
                    adr_id,
                    AuditEventType.CONFLICT_DETECTED,
                    {"error": str(result), "partial_failure": True},
                )
        return conflicts

    async def get_adr(self, adr_id: str) -> ADRRecord:
        row = await self.db.fetch_one("SELECT * FROM adrs WHERE id = ?", (adr_id,))
        if row is None:
            raise ADRMCPError("adr_not_found", "ADR not found.", {"adr_id": adr_id})
        record = self._row_to_record(row)
        record.audit_log = await self._get_audit_log(adr_id)
        record.supersession_chain = await self._get_supersession_chain(adr_id)
        return record

    async def deprecate_adr(
        self,
        adr_id: str,
        reason: str,
        superseded_by: str | None = None,
    ) -> ADRRecord:
        record = await self.get_adr(adr_id)
        if record.status is ADRStatus.DEPRECATED or record.status == ADRStatus.DEPRECATED:
            raise ADRMCPError(
                "adr_already_deprecated",
                "Cannot deprecate an ADR that is already DEPRECATED.",
                {"adr_id": adr_id},
            )

        if superseded_by:
            replacement = await self.get_adr(superseded_by)
            if replacement.status is ADRStatus.DEPRECATED or replacement.status == ADRStatus.DEPRECATED:
                raise ADRMCPError(
                    "invalid_supersession",
                    "A DEPRECATED ADR cannot supersede another ADR.",
                    {"adr_id": adr_id, "superseded_by": superseded_by},
                )

        now = self._now()
        async with self.db.write_lock:
            await self.db.conn.execute(
                """
                UPDATE adrs
                SET status = ?, supersedes = COALESCE(?, supersedes), updated_at = ?
                WHERE id = ?
                """,
                (ADRStatus.DEPRECATED.value, superseded_by, now, adr_id),
            )
            await self.db.conn.commit()
        await self._append_audit(
            adr_id,
            AuditEventType.DEPRECATED,
            {"reason": reason, "superseded_by": superseded_by},
        )
        return await self.get_adr(adr_id)

    async def summarize_project(
        self,
        project_id: str | None = None,
        include_deprecated: bool = False,
    ) -> SummaryResult:
        records = await self._list_records(project_id=project_id, include_deprecated=include_deprecated)
        context = "\n\n".join(self._record_text(record) for record in records)
        token_estimate = self.ai.estimate_tokens(context)
        hierarchical = token_estimate > self.settings.adr_summary_token_budget
        if not hierarchical:
            summary = await self.ai.summarize(records)
            return SummaryResult(summary=summary, adr_count=len(records), token_estimate=token_estimate)

        summary = await self._hierarchical_summary(records, depth=0)
        return SummaryResult(
            summary=summary,
            adr_count=len(records),
            token_estimate=token_estimate,
            hierarchical=True,
        )

    async def list_adrs(
        self,
        project_id: str | None = None,
        status: ADRStatus | None = None,
        tags: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedADRList:
        request = ListADRsInput(
            project_id=project_id,
            status=status,
            tags=tags,
            page=page,
            page_size=page_size,
        )
        records = await self._get_records_for_search(status=request.status, tags=request.tags, project_id=project_id)
        total = len(records)
        start = (request.page - 1) * request.page_size
        selected = records[start : start + request.page_size]
        items = [
            ADRSearchResult(
                id=record.id,
                title=record.title,
                score=1.0,
                snippet=self._snippet(record),
                tags=record.tags,
                status=record.status,
            )
            for record in selected
        ]
        return PaginatedADRList(items=items, total=total, page=request.page, page_size=request.page_size)

    async def reindex_embeddings(
        self,
        project_id: str | None = None,
        batch_size: int = 10,
        concurrency: int = 3,
    ) -> ReindexResult:
        records = await self._list_records(project_id=project_id, include_deprecated=True)
        failures: list[dict[str, str]] = []
        reindexed = 0
        semaphore = asyncio.Semaphore(concurrency)

        async def process(record: ADRRecord) -> bool:
            async with semaphore:
                try:
                    embedding = await self.ai.generate_embedding(self._record_text(record))
                    await self._upsert_embedding(record.id, embedding, self.settings.adr_embedding_model)
                    await self._append_audit(
                        record.id,
                        AuditEventType.REINDEXED,
                        {"embedding_model": self.settings.adr_embedding_model},
                    )
                    return True
                except Exception as exc:
                    failures.append({"adr_id": record.id, "error": str(exc)})
                    return False

        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            batch_results = await asyncio.gather(*(process(record) for record in batch))
            reindexed += sum(1 for ok in batch_results if ok)

        return ReindexResult(
            reindexed=reindexed,
            embedding_model=self.settings.adr_embedding_model,
            failures=failures,
        )

    async def _insert_adr(
        self,
        project_id: str,
        structure: ADRStructure,
        status: ADRStatus,
        author: str | None,
        embedding_model: str | None,
    ) -> ADRRecord:
        adr_id = str(uuid.uuid4())
        now = self._now()
        async with self.db.write_lock:
            await self.db.conn.execute(
                """
                INSERT INTO adrs(
                  id, project_id, title, status, context, decision, consequences,
                  options_json, tags_json, supersedes, created_at, updated_at, author,
                  embedding_model
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    adr_id,
                    project_id,
                    structure.title,
                    status.value,
                    structure.context,
                    structure.decision,
                    structure.consequences,
                    json.dumps(structure.options_considered),
                    json.dumps(structure.tags),
                    structure.supersedes,
                    now,
                    now,
                    author,
                    embedding_model,
                ),
            )
            await self.db.conn.commit()
        return await self.get_adr(adr_id)

    async def _append_audit(
        self,
        adr_id: str,
        event_type: AuditEventType,
        payload: dict[str, Any],
    ) -> None:
        async with self.db.write_lock:
            await self.db.conn.execute(
                """
                INSERT INTO adr_audit_log(adr_id, event_type, payload, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (adr_id, event_type.value, json.dumps(payload), self._now()),
            )
            await self.db.conn.commit()

    async def _upsert_embedding(self, adr_id: str, embedding: list[float], model: str) -> None:
        now = self._now()
        normalized = [float(value) for value in embedding]
        async with self.db.write_lock:
            await self.db.conn.execute(
                """
                INSERT INTO adr_embeddings(adr_id, embedding_json, embedding_model, dimensions, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(adr_id) DO UPDATE SET
                  embedding_json = excluded.embedding_json,
                  embedding_model = excluded.embedding_model,
                  dimensions = excluded.dimensions,
                  updated_at = excluded.updated_at
                """,
                (adr_id, json.dumps(normalized), model, len(normalized), now, now),
            )
            await self.db.conn.execute(
                "UPDATE adrs SET embedding_model = ?, updated_at = ? WHERE id = ?",
                (model, now, adr_id),
            )
            if self.db.sqlite_vec_enabled:
                await self._upsert_vec_table(adr_id, normalized)
            await self.db.conn.commit()

    async def _upsert_vec_table(self, adr_id: str, embedding: list[float]) -> None:
        try:  # pragma: no cover - depends on sqlite-vec host support.
            packed = json.dumps(embedding)
            await self.db.conn.execute("DELETE FROM vec_adrs WHERE adr_id = ?", (adr_id,))
            await self.db.conn.execute(
                "INSERT INTO vec_adrs(adr_id, embedding) VALUES (?, ?)",
                (adr_id, packed),
            )
        except Exception:
            self.db.sqlite_vec_enabled = False

    async def _get_embedding(self, adr_id: str) -> list[float] | None:
        row = await self.db.fetch_one(
            "SELECT embedding_json FROM adr_embeddings WHERE adr_id = ?",
            (adr_id,),
        )
        if row is None:
            return None
        return [float(value) for value in json.loads(row["embedding_json"])]

    async def _get_all_embeddings(self) -> dict[str, list[float]]:
        rows = await self.db.fetch_all("SELECT adr_id, embedding_json FROM adr_embeddings")
        return {row["adr_id"]: [float(value) for value in json.loads(row["embedding_json"])] for row in rows}

    async def _similar_candidates(self, source: ADRRecord, source_embedding: list[float]) -> list[ADRRecord]:
        records = await self._get_records_for_search(status=ADRStatus.ACCEPTED, project_id=source.project_id)
        embeddings = await self._get_all_embeddings()
        scored: list[tuple[float, ADRRecord]] = []
        for record in records:
            if record.id == source.id:
                continue
            embedding = embeddings.get(record.id)
            if not embedding:
                continue
            score = self._cosine_similarity(source_embedding, embedding)
            if score >= self.settings.adr_conflict_threshold:
                scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _score, record in scored[: self.settings.adr_max_conflicts]]

    async def _get_records_for_search(
        self,
        status: ADRStatus | None = None,
        tags: list[str] | None = None,
        project_id: str | None = None,
    ) -> list[ADRRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value if isinstance(status, ADRStatus) else str(status))
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        sql = "SELECT * FROM adrs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        rows = await self.db.fetch_all(sql, tuple(params))
        records = [self._row_to_record(row) for row in rows]
        if tags:
            normalized = {tag.strip().lower() for tag in tags if tag.strip()}
            records = [record for record in records if normalized.issubset(set(record.tags))]
        return records

    async def _list_records(self, project_id: str | None, include_deprecated: bool) -> list[ADRRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = ?")
            params.append(project_id)
        if not include_deprecated:
            clauses.append("status != ?")
            params.append(ADRStatus.DEPRECATED.value)
        sql = "SELECT * FROM adrs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC"
        rows = await self.db.fetch_all(sql, tuple(params))
        return [self._row_to_record(row) for row in rows]

    async def _get_audit_log(self, adr_id: str) -> list[AuditEvent]:
        rows = await self.db.fetch_all(
            "SELECT * FROM adr_audit_log WHERE adr_id = ? ORDER BY id ASC",
            (adr_id,),
        )
        return [
            AuditEvent(
                id=row["id"],
                adr_id=row["adr_id"],
                event_type=AuditEventType(row["event_type"]),
                payload=json.loads(row["payload"] or "{}"),
                timestamp=row["timestamp"],
            )
            for row in rows
        ]

    async def _get_supersession_chain(self, adr_id: str) -> list[str]:
        chain: list[str] = []
        current = adr_id
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            row = await self.db.fetch_one("SELECT supersedes FROM adrs WHERE id = ?", (current,))
            if row is None or row["supersedes"] is None:
                break
            current = str(row["supersedes"])
            chain.append(current)
        return chain

    async def _hierarchical_summary(self, records: list[ADRRecord], depth: int) -> str:
        if depth >= self.settings.adr_summary_max_depth or len(records) <= 5:
            return await self.ai.summarize(records)

        groups: dict[str, list[ADRRecord]] = {}
        for record in records:
            key = record.tags[0] if record.tags else "untagged"
            groups.setdefault(key, []).append(record)

        partials = []
        for tag, tag_records in groups.items():
            partial_summary = await self._hierarchical_summary(tag_records, depth + 1)
            partials.append(
                ADRRecord(
                    id=f"summary-{tag}",
                    project_id=records[0].project_id if records else "default",
                    title=f"Summary for {tag}",
                    status=ADRStatus.ACCEPTED,
                    context=partial_summary,
                    decision=partial_summary,
                    consequences="",
                    options_considered=[],
                    tags=[tag],
                    created_at=self._now(),
                    updated_at=self._now(),
                )
            )
        return await self.ai.summarize(partials)

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> ADRRecord:
        return ADRRecord(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            status=ADRStatus(row["status"]),
            context=row["context"],
            decision=row["decision"],
            consequences=row["consequences"],
            options_considered=json.loads(row["options_json"] or "[]"),
            tags=json.loads(row["tags_json"] or "[]"),
            supersedes=row["supersedes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            author=row["author"],
            embedding_model=row["embedding_model"],
        )

    @staticmethod
    def _draft_structure(raw_text: str) -> ADRStructure:
        first_line = next((line.strip() for line in raw_text.splitlines() if line.strip()), raw_text[:80])
        return ADRStructure(
            title=first_line[:120] or "Untitled ADR Draft",
            context=raw_text,
            decision="",
            options_considered=[],
            consequences="",
            tags=["draft"],
            supersedes=None,
        )

    @staticmethod
    def _structure_text(structure: ADRStructure) -> str:
        return "\n".join(
            [
                structure.title,
                structure.context,
                structure.decision,
                "\n".join(structure.options_considered),
                structure.consequences,
                " ".join(structure.tags),
            ]
        )

    @staticmethod
    def _record_text(record: ADRRecord) -> str:
        return "\n".join(
            [
                f"Title: {record.title}",
                f"Status: {record.status}",
                f"Context: {record.context}",
                f"Decision: {record.decision}",
                f"Options: {record.options_considered}",
                f"Consequences: {record.consequences}",
                f"Tags: {record.tags}",
            ]
        )

    @staticmethod
    def _snippet(record: ADRRecord, limit: int = 240) -> str:
        text = f"{record.context} {record.decision}".strip().replace("\n", " ")
        return text[: limit - 1] + "…" if len(text) > limit else text

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right:
            return 0.0
        length = min(len(left), len(right))
        dot = sum(left[i] * right[i] for i in range(length))
        left_norm = math.sqrt(sum(left[i] * left[i] for i in range(length)))
        right_norm = math.sqrt(sum(right[i] * right[i] for i in range(length)))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
