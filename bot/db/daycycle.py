"""CRUD for daycycle_meta (daily chat announce idempotency)."""

from __future__ import annotations

from bot.db.connection import Database


async def ensure_meta(db: Database) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO daycycle_meta (id, announced_day_key) VALUES (1, '')"
    )


async def get_announced_day_key(db: Database) -> str:
    await ensure_meta(db)
    row = await db.fetchone(
        "SELECT announced_day_key FROM daycycle_meta WHERE id = 1"
    )
    assert row is not None
    return str(row[0] or "")


async def set_announced_day_key(db: Database, day_key: str) -> None:
    await ensure_meta(db)
    await db.execute(
        "UPDATE daycycle_meta SET announced_day_key = ? WHERE id = 1",
        (str(day_key or ""),),
    )
