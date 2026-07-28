"""Migration 022: provider + album_id on queue_items."""

from __future__ import annotations

import aiosqlite

VERSION = 22
DESCRIPTION = "Колонки provider и album_id в queue_items"


async def upgrade(conn: aiosqlite.Connection) -> None:
    cur = await conn.execute("PRAGMA table_info(queue_items)")
    cols = {str(row[1]) for row in await cur.fetchall()}
    if "provider" not in cols:
        await conn.execute(
            "ALTER TABLE queue_items ADD COLUMN provider TEXT NOT NULL DEFAULT 'youtube'"
        )
    if "album_id" not in cols:
        await conn.execute(
            "ALTER TABLE queue_items ADD COLUMN album_id TEXT NOT NULL DEFAULT ''"
        )
    await conn.commit()
