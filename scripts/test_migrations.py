"""Test migration paths from legacy schema versions (run: python scripts/test_migrations.py)."""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import aiosqlite

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.db.migrate import get_schema_version
from bot.db.schema import SCHEMA_VERSION, init_schema

LEGACY = {
    1: """
        CREATE TABLE schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1, 1);
        CREATE TABLE points (user_id TEXT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE queue_meta (id INTEGER PRIMARY KEY CHECK (id = 1), current_json TEXT, current_token TEXT, token_counter INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE queue_items (position INTEGER PRIMARY KEY, video_id TEXT NOT NULL, requested_by TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL);
    """,
    2: """
        CREATE TABLE schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1, 2);
        CREATE TABLE queue_meta (id INTEGER PRIMARY KEY CHECK (id = 1), current_json TEXT, current_token TEXT, token_counter INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE queue_items (position INTEGER PRIMARY KEY, video_id TEXT NOT NULL, requested_by TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL, paid_cost INTEGER NOT NULL DEFAULT 0);
    """,
    3: """
        CREATE TABLE schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1, 3);
        CREATE TABLE queue_meta (id INTEGER PRIMARY KEY CHECK (id = 1), current_json TEXT, current_token TEXT, token_counter INTEGER NOT NULL DEFAULT 1, orders_enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE queue_items (position INTEGER PRIMARY KEY, video_id TEXT NOT NULL, requested_by TEXT NOT NULL, requested_by_name TEXT NOT NULL DEFAULT '', url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL, paid_cost INTEGER NOT NULL DEFAULT 0);
    """,
    4: """
        CREATE TABLE schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1, 4);
        CREATE TABLE user_names (user_id TEXT PRIMARY KEY, user_name TEXT NOT NULL DEFAULT '');
        CREATE TABLE queue_meta (id INTEGER PRIMARY KEY CHECK (id = 1), current_json TEXT, current_token TEXT, token_counter INTEGER NOT NULL DEFAULT 1, orders_enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE queue_items (position INTEGER PRIMARY KEY, video_id TEXT NOT NULL, requested_by TEXT NOT NULL, requested_by_name TEXT NOT NULL DEFAULT '', url TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL, paid_cost INTEGER NOT NULL DEFAULT 0);
    """,
    5: """
        CREATE TABLE schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1, 5);
        CREATE TABLE roulette_meta (id INTEGER PRIMARY KEY CHECK (id = 1), auto_enabled INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL DEFAULT 'IDLE', round_id INTEGER NOT NULL DEFAULT 0, round_opened_at REAL, closes_at REAL, cooldown_until REAL, collect_sec INTEGER NOT NULL DEFAULT 60, cooldown_sec INTEGER NOT NULL DEFAULT 180, last_result TEXT);
        INSERT INTO roulette_meta (id) VALUES (1);
        CREATE TABLE roulette_bets (id INTEGER PRIMARY KEY AUTOINCREMENT, round_id INTEGER NOT NULL, user_id TEXT NOT NULL, user_name TEXT NOT NULL DEFAULT '', amount INTEGER NOT NULL, bet_type TEXT NOT NULL, bet_payload TEXT NOT NULL, UNIQUE (round_id, user_id));
    """,
    6: """
        CREATE TABLE schema_version (id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1, 6);
        CREATE TABLE minigames_bank (id INTEGER PRIMARY KEY CHECK (id = 1), bank INTEGER NOT NULL DEFAULT 0);
        INSERT INTO minigames_bank VALUES (1, 12345);
        CREATE TABLE roulette_meta (id INTEGER PRIMARY KEY CHECK (id = 1), auto_enabled INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL DEFAULT 'IDLE', round_id INTEGER NOT NULL DEFAULT 0, round_opened_at REAL, closes_at REAL, cooldown_until REAL, collect_sec INTEGER NOT NULL DEFAULT 60, cooldown_sec INTEGER NOT NULL DEFAULT 180, last_result TEXT);
        INSERT INTO roulette_meta (id) VALUES (1);
    """,
}

REQUIRED_TABLES = [
    "minigames_bank",
    "roulette_meta",
    "roulette_bets",
    "races_meta",
    "races_bets",
    "races_lineup",
    "races_princess_stats",
]


async def check(start_ver: int) -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db_path = Path(path)
    try:
        async with aiosqlite.connect(db_path) as conn:
            await conn.executescript(LEGACY[start_ver])
            await conn.commit()
            await init_schema(conn, db_path=db_path)
            ver = await get_schema_version(conn)
            tables = {
                r[0]
                for r in await conn.execute_fetchall(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            missing = [t for t in REQUIRED_TABLES if t not in tables]
            rcols = {
                r[1] for r in await conn.execute_fetchall("PRAGMA table_info(roulette_meta)")
            }
            bank_row = await conn.execute_fetchall(
                "SELECT bank FROM minigames_bank WHERE id=1"
            )
            if "bank" in rcols:
                raise AssertionError(f"v{start_ver}: roulette_meta still has bank column")
            if missing:
                raise AssertionError(f"v{start_ver}: missing tables {missing}")
            if ver != SCHEMA_VERSION:
                raise AssertionError(f"v{start_ver}: version {ver} != {SCHEMA_VERSION}")
            print(f"[OK] from v{start_ver} -> v{ver}, minigames_bank={bank_row[0][0]}")
    finally:
        db_path.unlink(missing_ok=True)


async def main() -> int:
    for ver in sorted(LEGACY):
        await check(ver)
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
