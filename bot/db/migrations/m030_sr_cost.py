"""Migration 030: sr_cost on queue_meta."""

from __future__ import annotations

import aiosqlite

VERSION = 30
DESCRIPTION = "Колонка sr_cost в queue_meta"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(queue_meta)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "sr_cost" not in col_names:
        await conn.execute("ALTER TABLE queue_meta ADD COLUMN sr_cost INTEGER")
