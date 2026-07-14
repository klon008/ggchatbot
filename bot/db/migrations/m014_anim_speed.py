"""Migration 014: cards_meta.anim_speed — множитель скорости OBS-анимации."""

from __future__ import annotations

import aiosqlite

VERSION = 14
DESCRIPTION = "Колонка anim_speed в cards_meta"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(cards_meta)") as cursor:
        cols = await cursor.fetchall()
    col_names = {r[1] for r in cols}
    if "anim_speed" not in col_names:
        await conn.execute(
            "ALTER TABLE cards_meta ADD COLUMN anim_speed REAL NOT NULL DEFAULT 1.0"
        )
