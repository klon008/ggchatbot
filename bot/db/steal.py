"""Steal statistics and atomic steal execution."""

from __future__ import annotations

from typing import Any

from .connection import Database

DEFAULT_INFO: dict[str, Any] = {
    "attempts": 0,
    "success": 0,
    "stolen_total": 0,
    "chance": 3,
    "last_time": 0.0,
    "times_in_jail": 0,
}


async def ensure_user(db: Database, user_id: str) -> None:
    uid = str(user_id)
    await db.execute(
        "INSERT OR IGNORE INTO steal_stats "
        "(user_id, attempts, success, stolen_total, chance, last_time, times_in_jail) "
        "VALUES (?, 0, 0, 0, 3, 0, 0)",
        (uid,),
    )


async def get_info(db: Database, user_id: str) -> dict[str, Any]:
    uid = str(user_id)
    await ensure_user(db, uid)
    row = await db.fetchone("SELECT * FROM steal_stats WHERE user_id = ?", (uid,))
    if row is None:
        return dict(DEFAULT_INFO)
    return {
        "attempts": int(row["attempts"]),
        "success": int(row["success"]),
        "stolen_total": int(row["stolen_total"]),
        "chance": int(row["chance"]),
        "last_time": float(row["last_time"]),
        "times_in_jail": int(row["times_in_jail"]),
    }


async def save_info(db: Database, user_id: str, info: dict[str, Any]) -> None:
    uid = str(user_id)
    await ensure_user(db, uid)
    await db.execute(
        "UPDATE steal_stats SET "
        "attempts = ?, success = ?, stolen_total = ?, chance = ?, "
        "last_time = ?, times_in_jail = ? "
        "WHERE user_id = ?",
        (
            int(info.get("attempts", 0)),
            int(info.get("success", 0)),
            int(info.get("stolen_total", 0)),
            int(info.get("chance", 3)),
            float(info.get("last_time", 0)),
            int(info.get("times_in_jail", 0)),
            uid,
        ),
    )


async def record_steal_success(db: Database, thief_id: str, amount: int) -> None:
    """Update thief steal stats after a successful steal (points handled separately)."""
    thief = str(thief_id)
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO steal_stats "
            "(user_id, attempts, success, stolen_total, chance, last_time, times_in_jail) "
            "VALUES (?, 0, 0, 0, 3, 0, 0)",
            (thief,),
        )
        await conn.execute(
            "UPDATE steal_stats SET "
            "success = success + 1, stolen_total = stolen_total + ? "
            "WHERE user_id = ?",
            (amount, thief),
        )


async def increment_jail_count(db: Database, user_id: str) -> None:
    uid = str(user_id)
    await ensure_user(db, uid)
    await db.execute(
        "UPDATE steal_stats SET times_in_jail = times_in_jail + 1 WHERE user_id = ?",
        (uid,),
    )
