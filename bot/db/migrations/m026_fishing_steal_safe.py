"""Migration 026: pocket safe (steal protection) on fishing_players."""

from __future__ import annotations

import aiosqlite

VERSION = 26
DESCRIPTION = "Колонка steal_safe в fishing_players (карманный сейф)"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(fishing_players)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "steal_safe" not in col_names:
        await conn.execute(
            "ALTER TABLE fishing_players "
            "ADD COLUMN steal_safe INTEGER NOT NULL DEFAULT 0"
        )
