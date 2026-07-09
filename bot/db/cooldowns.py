"""Dice cooldown persistence."""

from __future__ import annotations

from .connection import Database


async def get_last(db: Database, user_id: str) -> float:
    row = await db.fetchone(
        "SELECT last_time FROM dice_cooldowns WHERE user_id = ?",
        (str(user_id),),
    )
    return float(row["last_time"]) if row else 0.0


async def set_last(db: Database, user_id: str, last_time: float) -> None:
    await db.execute(
        "INSERT INTO dice_cooldowns (user_id, last_time) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET last_time = excluded.last_time",
        (str(user_id), last_time),
    )
