"""Async SQLite connection with WAL and transaction helper."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Optional

import aiosqlite

from .schema import init_schema

log = logging.getLogger("bot.db")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def default_db_path() -> Path:
    return DATA_DIR / "bot.db"


class Database:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or default_db_path()
        self._conn: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not open")
        return self._conn

    async def open(self) -> None:
        if self._conn is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await init_schema(self._conn)
        log.info("SQLite opened: %s", self.path)

    async def close(self) -> None:
        if self._conn is None:
            return
        await self._conn.close()
        self._conn = None
        log.info("SQLite closed.")

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            await self.conn.commit()
            return cursor

    async def executemany(self, sql: str, params_seq) -> None:
        async with self._lock:
            await self.conn.executemany(sql, params_seq)
            await self.conn.commit()

    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[aiosqlite.Row]:
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: tuple = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            cursor = await self.conn.execute(sql, params)
            return await cursor.fetchall()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._lock:
            await self.conn.execute("BEGIN")
            try:
                yield self.conn
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise
