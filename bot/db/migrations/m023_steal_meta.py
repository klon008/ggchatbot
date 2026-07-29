"""Migration 023: steal_meta for admin override of !кража schedule."""

from __future__ import annotations

import aiosqlite

VERSION = 23
DESCRIPTION = "Таблица steal_meta — ручной override расписания кражи"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steal_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            override_enabled INTEGER NOT NULL DEFAULT 0,
            override_until REAL,
            last_schedule_open_key TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await conn.execute(
        "INSERT OR IGNORE INTO steal_meta "
        "(id, override_enabled, override_until, last_schedule_open_key) "
        "VALUES (1, 0, NULL, '')"
    )
