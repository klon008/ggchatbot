"""Migration 007: races tables."""

from __future__ import annotations

import aiosqlite

VERSION = 7
DESCRIPTION = "Таблицы races_meta, races_bets, races_lineup, races_princess_stats"

_DEFAULT_COLLECT_SEC = 60
_DEFAULT_COOLDOWN_SEC = 180
_DEFAULT_RACE_DELAY_SEC = 10


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS races_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            auto_enabled INTEGER NOT NULL DEFAULT 1,
            state TEXT NOT NULL DEFAULT 'IDLE',
            round_id INTEGER NOT NULL DEFAULT 0,
            round_opened_at REAL,
            closes_at REAL,
            cooldown_until REAL,
            collect_sec INTEGER NOT NULL DEFAULT 60,
            cooldown_sec INTEGER NOT NULL DEFAULT 180,
            race_delay_sec INTEGER NOT NULL DEFAULT 10,
            last_result TEXT,
            race_progress TEXT,
            fixed_odds TEXT
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS races_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            amount INTEGER NOT NULL,
            horse_number INTEGER NOT NULL,
            UNIQUE (round_id, user_id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS races_lineup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            horse_number INTEGER NOT NULL,
            princess_name TEXT NOT NULL,
            UNIQUE (round_id, horse_number)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS races_princess_stats (
            princess_name TEXT PRIMARY KEY,
            races_count INTEGER NOT NULL DEFAULT 0,
            wins_count INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await conn.execute(
        """
        INSERT OR IGNORE INTO races_meta (
            id, auto_enabled, state, round_id,
            collect_sec, cooldown_sec, race_delay_sec
        ) VALUES (1, 1, 'IDLE', 0, ?, ?, ?)
        """,
        (_DEFAULT_COLLECT_SEC, _DEFAULT_COOLDOWN_SEC, _DEFAULT_RACE_DELAY_SEC),
    )
