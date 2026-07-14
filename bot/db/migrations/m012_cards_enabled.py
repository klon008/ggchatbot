"""Migration 012: cards_meta.enabled — глобальный выключатель команд карт."""

from __future__ import annotations

import aiosqlite

VERSION = 12
DESCRIPTION = "Колонка enabled в cards_meta"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(cards_meta)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "enabled" not in col_names:
        await conn.execute(
            "ALTER TABLE cards_meta ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1"
        )
