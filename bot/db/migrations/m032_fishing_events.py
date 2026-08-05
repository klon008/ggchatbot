"""Migration 032: fishing events schedule + per-player grant day key."""

from __future__ import annotations

import aiosqlite

VERSION = 32
DESCRIPTION = "fishing_meta.events_json и fishing_players.event_boost_day_key"


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(fishing_meta)") as cursor:
        meta_cols = {c[1] for c in await cursor.fetchall()}
    if "events_json" not in meta_cols:
        await conn.execute(
            "ALTER TABLE fishing_meta ADD COLUMN events_json TEXT NOT NULL DEFAULT ''"
        )

    async with conn.execute("PRAGMA table_info(fishing_players)") as cursor:
        player_cols = {c[1] for c in await cursor.fetchall()}
    if "event_boost_day_key" not in player_cols:
        await conn.execute(
            "ALTER TABLE fishing_players "
            "ADD COLUMN event_boost_day_key TEXT NOT NULL DEFAULT ''"
        )
