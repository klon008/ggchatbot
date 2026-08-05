"""Migration 033: fishing_grant_log for admin manual grants."""

from __future__ import annotations

import aiosqlite

VERSION = 33
DESCRIPTION = "Таблица fishing_grant_log — лог ручных выдач ивентов"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fishing_grant_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            actor TEXT NOT NULL DEFAULT 'admin',
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            item TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            note TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fishing_grant_log_created "
        "ON fishing_grant_log(created_at DESC)"
    )
