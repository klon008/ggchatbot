"""Migration 036: princess events schedule + per-user bonus grants."""

from __future__ import annotations

import aiosqlite

VERSION = 36
DESCRIPTION = "princess_meta.events_json и princess_bonus_grants"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS princess_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            events_json TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await conn.execute(
        "INSERT OR IGNORE INTO princess_meta (id, events_json) VALUES (1, '')"
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS princess_bonus_grants (
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            day_key TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (user_id, kind)
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_princess_bonus_grants_kind_day "
        "ON princess_bonus_grants(kind, day_key)"
    )
