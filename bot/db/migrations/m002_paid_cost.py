"""Migration 002: paid_cost column on queue_items."""

from __future__ import annotations

import aiosqlite

VERSION = 2
DESCRIPTION = "Колонка paid_cost в queue_items"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(queue_items)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "paid_cost" not in col_names:
        await conn.execute(
            "ALTER TABLE queue_items ADD COLUMN paid_cost INTEGER NOT NULL DEFAULT 0"
        )
