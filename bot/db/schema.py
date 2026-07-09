"""Database schema initialization."""

from __future__ import annotations

import aiosqlite

SCHEMA_VERSION = 2

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL
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
    token_counter INTEGER NOT NULL DEFAULT 1
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
"""


async def _migrate_schema(conn: aiosqlite.Connection) -> None:
    async with conn.execute("SELECT version FROM schema_version WHERE id = 1") as cursor:
        row = await cursor.fetchone()
    version = int(row[0]) if row else 1

    if version < 2:
        async with conn.execute("PRAGMA table_info(queue_items)") as cursor:
            cols = await cursor.fetchall()
        col_names = {c[1] for c in cols}
        if "paid_cost" not in col_names:
            await conn.execute(
                "ALTER TABLE queue_items ADD COLUMN paid_cost INTEGER NOT NULL DEFAULT 0"
            )
        await conn.execute("UPDATE schema_version SET version = 2 WHERE id = 1")


async def init_schema(conn: aiosqlite.Connection) -> None:
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
    await _migrate_schema(conn)
    await conn.commit()
