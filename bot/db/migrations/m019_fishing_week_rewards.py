"""Migration 019: admin-editable week rewards JSON on fishing_meta."""

from __future__ import annotations

import aiosqlite

VERSION = 19
DESCRIPTION = "fishing_meta.week_rewards_json — награды недели из админки"


async def upgrade(conn: aiosqlite.Connection) -> None:
    cur = await conn.execute("PRAGMA table_info(fishing_meta)")
    cols = {str(row[1]) for row in await cur.fetchall()}
    if "week_rewards_json" not in cols:
        await conn.execute(
            "ALTER TABLE fishing_meta ADD COLUMN week_rewards_json TEXT NOT NULL DEFAULT ''"
        )
        await conn.commit()
