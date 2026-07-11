"""Migration 005: roulette_meta and roulette_bets tables."""

from __future__ import annotations

import aiosqlite

VERSION = 5
DESCRIPTION = "Таблицы roulette_meta и roulette_bets"

_DEFAULT_BANK = 50_000
_DEFAULT_COLLECT_SEC = 60
_DEFAULT_COOLDOWN_SEC = 180


async def _roulette_meta_columns(conn: aiosqlite.Connection) -> set[str]:
    rows = await conn.execute_fetchall("PRAGMA table_info(roulette_meta)")
    return {str(row[1]) for row in rows}


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS roulette_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            bank INTEGER NOT NULL DEFAULT 0,
            auto_enabled INTEGER NOT NULL DEFAULT 1,
            state TEXT NOT NULL DEFAULT 'IDLE',
            round_id INTEGER NOT NULL DEFAULT 0,
            round_opened_at REAL,
            closes_at REAL,
            cooldown_until REAL,
            collect_sec INTEGER NOT NULL DEFAULT 60,
            cooldown_sec INTEGER NOT NULL DEFAULT 180,
            last_result TEXT
        )
        """
    )

    columns = await _roulette_meta_columns(conn)
    if "bank" not in columns:
        await conn.execute(
            "ALTER TABLE roulette_meta ADD COLUMN bank INTEGER NOT NULL DEFAULT 0"
        )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS roulette_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            amount INTEGER NOT NULL,
            bet_type TEXT NOT NULL,
            bet_payload TEXT NOT NULL,
            UNIQUE (round_id, user_id)
        )
        """
    )
    await conn.execute(
        """
        INSERT OR IGNORE INTO roulette_meta (
            id, bank, auto_enabled, state, round_id,
            collect_sec, cooldown_sec
        ) VALUES (1, ?, 1, 'IDLE', 0, ?, ?)
        """,
        (_DEFAULT_BANK, _DEFAULT_COLLECT_SEC, _DEFAULT_COOLDOWN_SEC),
    )
