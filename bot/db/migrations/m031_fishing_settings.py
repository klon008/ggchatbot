"""Migration 031: fishing_meta.settings_json — runtime costs/chances from admin."""

from __future__ import annotations

import aiosqlite

VERSION = 31
DESCRIPTION = "fishing_meta.settings_json — настройки рыбалки из админки"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(fishing_meta)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "settings_json" not in col_names:
        await conn.execute(
            "ALTER TABLE fishing_meta ADD COLUMN settings_json TEXT NOT NULL DEFAULT ''"
        )
