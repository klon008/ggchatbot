"""Migration 024: block_ym_explicit flag on queue_meta."""

from __future__ import annotations

import aiosqlite

VERSION = 24
DESCRIPTION = "Колонка block_ym_explicit в queue_meta"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(queue_meta)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "block_ym_explicit" not in col_names:
        await conn.execute(
            "ALTER TABLE queue_meta ADD COLUMN block_ym_explicit INTEGER NOT NULL DEFAULT 1"
        )
