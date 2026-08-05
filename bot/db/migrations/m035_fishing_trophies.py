"""Migration 035: fishing_trophies — all-time heaviest per species."""

from __future__ import annotations

import aiosqlite

VERSION = 35
DESCRIPTION = "Таблица fishing_trophies — зал славы по видам (без автосброса)"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fishing_trophies (
            species TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL,
            achieved_at REAL NOT NULL
        )
        """
    )
