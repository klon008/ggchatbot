"""Migration 029: queue size/duration/cooldown limits on queue_meta."""

from __future__ import annotations

import aiosqlite

VERSION = 29
DESCRIPTION = "Колонки лимитов очереди в queue_meta"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(queue_meta)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    for name in (
        "max_queue_size",
        "max_duration_sec",
        "track_watchdog_extra_sec",
        "user_cooldown_sec",
    ):
        if name not in col_names:
            await conn.execute(f"ALTER TABLE queue_meta ADD COLUMN {name} INTEGER")
