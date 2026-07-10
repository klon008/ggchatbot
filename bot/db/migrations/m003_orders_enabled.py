"""Migration 003: orders_enabled flag on queue_meta."""

from __future__ import annotations

import aiosqlite

VERSION = 3
DESCRIPTION = "Колонка orders_enabled в queue_meta"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(queue_meta)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "orders_enabled" not in col_names:
        await conn.execute(
            "ALTER TABLE queue_meta ADD COLUMN orders_enabled INTEGER NOT NULL DEFAULT 1"
        )
