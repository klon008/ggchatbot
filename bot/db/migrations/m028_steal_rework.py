"""Migration 028: steal rework — wipe stats, miss-decay key, loot tiers override."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import aiosqlite

VERSION = 28
DESCRIPTION = (
    "Вайп steal_stats (+JSON backup), last_steal_day_key, "
    "steal_meta miss-decay + loot_tiers"
)

log = logging.getLogger("bot.db")
MSK = ZoneInfo("Europe/Moscow")


async def upgrade(conn: aiosqlite.Connection) -> None:
    await _backup_and_wipe_steal_stats(conn)
    await _ensure_steal_stats_column(conn)
    await _ensure_steal_meta_columns(conn)


async def _backup_and_wipe_steal_stats(conn: aiosqlite.Connection) -> None:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='steal_stats'"
    ) as cur:
        if await cur.fetchone() is None:
            return

    async with conn.execute("SELECT * FROM steal_stats") as cur:
        rows = await cur.fetchall()
        col_names = [d[0] for d in cur.description] if cur.description else []

    payload_rows = []
    for row in rows:
        item = {}
        for i, name in enumerate(col_names):
            val = row[i]
            if isinstance(val, bytes):
                val = val.decode("utf-8", errors="replace")
            item[name] = val
        payload_rows.append(item)

    day = datetime.now(MSK).strftime("%Y%m%d")
    backups = _backups_dir(conn)
    backups.mkdir(parents=True, exist_ok=True)
    path = backups / f"steal_stats_wipe_{day}.json"
    stamped = datetime.now(MSK).isoformat()
    path.write_text(
        json.dumps(
            {"wiped_at": stamped, "rows": payload_rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log.info("steal_stats backup: %s (%d rows)", path, len(payload_rows))

    await conn.execute("DELETE FROM steal_stats")


def _backups_dir(conn: aiosqlite.Connection) -> Path:
    """data/backups next to repo data/ directory."""
    data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"
    return data_dir / "backups"


async def _ensure_steal_stats_column(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(steal_stats)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "last_steal_day_key" not in cols:
        await conn.execute(
            "ALTER TABLE steal_stats ADD COLUMN "
            "last_steal_day_key TEXT NOT NULL DEFAULT ''"
        )


async def _ensure_steal_meta_columns(conn: aiosqlite.Connection) -> None:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='steal_meta'"
    ) as cur:
        if await cur.fetchone() is None:
            await conn.execute(
                """
                CREATE TABLE steal_meta (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    override_enabled INTEGER NOT NULL DEFAULT 0,
                    override_until REAL,
                    last_schedule_open_key TEXT NOT NULL DEFAULT '',
                    last_miss_decay_day_key TEXT NOT NULL DEFAULT '',
                    loot_tiers_json TEXT
                )
                """
            )
            await conn.execute(
                "INSERT OR IGNORE INTO steal_meta "
                "(id, override_enabled, override_until, last_schedule_open_key, "
                "last_miss_decay_day_key, loot_tiers_json) "
                "VALUES (1, 0, NULL, '', '', NULL)"
            )
            return

    async with conn.execute("PRAGMA table_info(steal_meta)") as cur:
        cols = {row[1] for row in await cur.fetchall()}
    if "last_miss_decay_day_key" not in cols:
        await conn.execute(
            "ALTER TABLE steal_meta ADD COLUMN "
            "last_miss_decay_day_key TEXT NOT NULL DEFAULT ''"
        )
    if "loot_tiers_json" not in cols:
        await conn.execute(
            "ALTER TABLE steal_meta ADD COLUMN loot_tiers_json TEXT"
        )
    await conn.execute(
        "INSERT OR IGNORE INTO steal_meta "
        "(id, override_enabled, override_until, last_schedule_open_key) "
        "VALUES (1, 0, NULL, '')"
    )
