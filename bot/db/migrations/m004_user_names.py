"""Migration 004: user_names table + backfill from queue_items."""

from __future__ import annotations

import aiosqlite

VERSION = 4
DESCRIPTION = "Таблица user_names + backfill из queue_items"


async def upgrade(conn: aiosqlite.Connection) -> None:
    qi_cols = {
        row[1]
        for row in await conn.execute_fetchall("PRAGMA table_info(queue_items)")
    }
    if "requested_by_name" not in qi_cols:
        await conn.execute(
            "ALTER TABLE queue_items ADD COLUMN requested_by_name TEXT NOT NULL DEFAULT ''"
        )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_names (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await conn.execute(
        """
        INSERT INTO user_names (user_id, user_name)
        SELECT qi.requested_by, qi.requested_by_name
        FROM queue_items qi
        INNER JOIN (
            SELECT requested_by, MAX(added_at) AS max_added
            FROM queue_items
            WHERE requested_by_name != ''
            GROUP BY requested_by
        ) latest ON qi.requested_by = latest.requested_by
                AND qi.added_at = latest.max_added
        WHERE qi.requested_by_name != ''
        ON CONFLICT(user_id) DO UPDATE SET user_name = excluded.user_name
        WHERE excluded.user_name != ''
        """
    )
