"""Database schema initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite

from .migrations import MIGRATIONS

SCHEMA_VERSION = max(m.VERSION for m in MIGRATIONS)

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_names (
    user_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS points (
    user_id TEXT PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS steal_stats (
    user_id TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    stolen_total INTEGER NOT NULL DEFAULT 0,
    chance INTEGER NOT NULL DEFAULT 3,
    last_time REAL NOT NULL DEFAULT 0,
    times_in_jail INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_month TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_progress (
    user_id TEXT NOT NULL,
    month TEXT NOT NULL,
    counter INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, month)
);

CREATE TABLE IF NOT EXISTS daily_claims (
    user_id TEXT NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS queue_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_json TEXT,
    current_token TEXT,
    token_counter INTEGER NOT NULL DEFAULT 1,
    orders_enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS queue_items (
    position INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_by_name TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    added_at REAL NOT NULL,
    paid_cost INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prison (
    user_id TEXT PRIMARY KEY,
    release_time REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS dice_cooldowns (
    user_id TEXT PRIMARY KEY,
    last_time REAL NOT NULL
);

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
);

CREATE TABLE IF NOT EXISTS roulette_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL,
    bet_type TEXT NOT NULL,
    bet_payload TEXT NOT NULL,
    UNIQUE (round_id, user_id)
);
"""


async def init_schema(
    conn: aiosqlite.Connection,
    *,
    db_path: Optional[Path] = None,
) -> None:
    await conn.executescript(TABLES_SQL)
    await conn.execute(
        "INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, ?)",
        (SCHEMA_VERSION,),
    )
    await conn.execute("INSERT OR IGNORE INTO daily_meta (id, current_month) VALUES (1, '')")
    await conn.execute(
        "INSERT OR IGNORE INTO queue_meta (id, current_json, current_token, token_counter) "
        "VALUES (1, NULL, NULL, 1)"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO roulette_meta (id, bank, auto_enabled, state, round_id, collect_sec, cooldown_sec) "
        "VALUES (1, 50000, 1, 'IDLE', 0, 60, 180)"
    )
    from .migrate import run_migrations

    await run_migrations(conn, db_path=db_path)
    await conn.commit()
