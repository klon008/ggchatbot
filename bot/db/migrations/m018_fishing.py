"""Migration 018: fishing module tables."""

from __future__ import annotations

import aiosqlite

VERSION = 18
DESCRIPTION = "Таблицы fishing_players, fishing_records, fishing_week_weights, fishing_meta"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fishing_players (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL DEFAULT '',
            energy INTEGER NOT NULL DEFAULT 100,
            energy_updated_at REAL NOT NULL DEFAULT 0,
            worms INTEGER NOT NULL DEFAULT 0,
            maggots INTEGER NOT NULL DEFAULT 0,
            rod_state TEXT NOT NULL DEFAULT 'none',
            last_cast_at REAL NOT NULL DEFAULT 0,
            day_key TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fishing_records (
            user_id TEXT NOT NULL,
            species TEXT NOT NULL,
            weight REAL NOT NULL,
            PRIMARY KEY (user_id, species)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fishing_week_weights (
            week_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            species TEXT NOT NULL,
            weight REAL NOT NULL,
            achieved_at REAL NOT NULL,
            PRIMARY KEY (week_id, user_id, species)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fishing_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            day_key TEXT NOT NULL DEFAULT '',
            first_fish_claimed INTEGER NOT NULL DEFAULT 0,
            current_week_id TEXT NOT NULL DEFAULT '',
            pending_rewards_week_id TEXT NOT NULL DEFAULT ''
        )
        """
    )
    await conn.execute(
        "INSERT OR IGNORE INTO fishing_meta "
        "(id, day_key, first_fish_claimed, current_week_id, pending_rewards_week_id) "
        "VALUES (1, '', 0, '', '')"
    )
