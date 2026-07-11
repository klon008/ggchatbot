"""Migration 006: shared minigames_bank, remove bank from roulette_meta."""

from __future__ import annotations

import aiosqlite

VERSION = 6
DESCRIPTION = "Общая казна minigames_bank"

_DEFAULT_BANK = 50_000


async def _roulette_meta_columns(conn: aiosqlite.Connection) -> set[str]:
    rows = await conn.execute_fetchall("PRAGMA table_info(roulette_meta)")
    return {str(row[1]) for row in rows}


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS minigames_bank (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            bank INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    columns = await _roulette_meta_columns(conn)
    if "bank" in columns:
        row = await conn.execute_fetchall("SELECT bank FROM roulette_meta WHERE id = 1")
        existing_bank = int(row[0][0]) if row else _DEFAULT_BANK
    else:
        row = await conn.execute_fetchall("SELECT bank FROM minigames_bank WHERE id = 1")
        existing_bank = int(row[0][0]) if row else _DEFAULT_BANK

    await conn.execute(
        "INSERT OR IGNORE INTO minigames_bank (id, bank) VALUES (1, ?)",
        (existing_bank,),
    )

    if "bank" not in columns:
        return

    await conn.execute(
        """
        CREATE TABLE roulette_meta_new (
            id INTEGER PRIMARY KEY CHECK (id = 1),
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
    await conn.execute(
        """
        INSERT INTO roulette_meta_new (
            id, auto_enabled, state, round_id, round_opened_at,
            closes_at, cooldown_until, collect_sec, cooldown_sec, last_result
        )
        SELECT
            id, auto_enabled, state, round_id, round_opened_at,
            closes_at, cooldown_until, collect_sec, cooldown_sec, last_result
        FROM roulette_meta
        """
    )
    await conn.execute("DROP TABLE roulette_meta")
    await conn.execute("ALTER TABLE roulette_meta_new RENAME TO roulette_meta")
