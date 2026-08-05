"""Migration 034: daycycle_meta for daily chat announce idempotency."""

from __future__ import annotations

import aiosqlite

VERSION = 34
DESCRIPTION = "Таблица daycycle_meta — ключ анонса смены суток"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daycycle_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            announced_day_key TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await conn.execute(
        "INSERT OR IGNORE INTO daycycle_meta (id, announced_day_key) VALUES (1, '')"
    )
