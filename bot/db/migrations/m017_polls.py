"""Migration 017: poll (predictions) tables."""

from __future__ import annotations

import aiosqlite

VERSION = 17
DESCRIPTION = "Таблицы poll_meta, poll_bets"

_DEFAULT_COLLECT_SEC = 300


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS poll_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            state TEXT NOT NULL DEFAULT 'IDLE',
            round_id INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            options TEXT NOT NULL DEFAULT '[]',
            round_opened_at REAL,
            closes_at REAL,
            collect_sec INTEGER NOT NULL DEFAULT 300,
            winning_option INTEGER,
            last_result TEXT
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS poll_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            amount INTEGER NOT NULL,
            option_index INTEGER NOT NULL,
            UNIQUE (round_id, user_id)
        )
        """
    )
    await conn.execute(
        """
        INSERT OR IGNORE INTO poll_meta (
            id, state, round_id, title, options, collect_sec
        ) VALUES (1, 'IDLE', 0, '', '[]', ?)
        """,
        (_DEFAULT_COLLECT_SEC,),
    )
