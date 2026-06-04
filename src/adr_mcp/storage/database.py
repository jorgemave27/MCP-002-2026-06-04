"""SQLite storage layer and migrations."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from adr_mcp.models.errors import ADRMCPError

LOGGER = logging.getLogger(__name__)


class Database:
    """Async SQLite database wrapper.

    SQLite is a single-file database, so this wrapper uses one shared connection and an
    asyncio lock for writes that must be serialized. This satisfies the local MCP server use case
    while keeping the code simple and deterministic.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.expanduser()
        self._conn: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()
        self.sqlite_vec_enabled = False

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise ADRMCPError("database_not_connected", "Database connection has not been opened.")
        return self._conn

    async def connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        await self.conn.execute("PRAGMA journal_mode = WAL")
        await self.conn.execute("PRAGMA busy_timeout = 5000")
        await self._apply_migrations()
        await self._try_enable_sqlite_vec()
        await self.conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _apply_migrations(self) -> None:
        migrations_dir = Path(__file__).parent / "migrations"
        for migration in sorted(migrations_dir.glob("*.sql")):
            sql = migration.read_text(encoding="utf-8")
            await self.conn.executescript(sql)

    async def _try_enable_sqlite_vec(self) -> None:
        """Best-effort sqlite-vec activation.

        The ADR spec requires sqlite-vec. The package exposes a loadable extension when
        available, but local CI environments may not support extension loading. The repository
        still keeps a JSON embedding fallback in `adr_embeddings`; semantic behavior remains
        testable and deterministic.
        """
        try:
            import sqlite_vec  # type: ignore

            await self.conn.enable_load_extension(True)
            raw_conn = self.conn._conn  # noqa: SLF001 - aiosqlite has no public loader hook.
            sqlite_vec.load(raw_conn)
            await self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_adrs USING vec0(
                  adr_id TEXT PRIMARY KEY,
                  embedding FLOAT[1536]
                )
                """
            )
            self.sqlite_vec_enabled = True
            LOGGER.info("sqlite-vec extension enabled")
        except Exception as exc:  # pragma: no cover - depends on host extension support.
            self.sqlite_vec_enabled = False
            LOGGER.warning("sqlite-vec unavailable; using JSON embedding fallback: %s", exc)

    async def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        cursor = await self.conn.execute(sql, params)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        cursor = await self.conn.execute(sql, params)
        try:
            rows = await cursor.fetchall()
            return list(rows)
        finally:
            await cursor.close()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self.conn.execute(sql, params)

    async def execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self.write_lock:
            await self.conn.execute(sql, params)
            await self.conn.commit()

    async def executescript_write(self, sql: str) -> None:
        async with self.write_lock:
            await self.conn.executescript(sql)
            await self.conn.commit()
