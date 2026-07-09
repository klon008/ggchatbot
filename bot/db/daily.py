"""Daily bonus progress and claims."""

from __future__ import annotations

from typing import Any

from .connection import Database


async def get_current_month(db: Database) -> str:
    row = await db.fetchone("SELECT current_month FROM daily_meta WHERE id = 1")
    return str(row["current_month"]) if row else ""


async def set_current_month(db: Database, month: str) -> None:
    await db.execute(
        "UPDATE daily_meta SET current_month = ? WHERE id = 1",
        (month,),
    )


async def load_user_progress(db: Database, month: str) -> dict[str, int]:
    rows = await db.fetchall(
        "SELECT user_id, counter FROM daily_progress WHERE month = ?",
        (month,),
    )
    return {str(row["user_id"]): int(row["counter"]) for row in rows}


async def save_user_progress(db: Database, month: str, progress: dict[str, int]) -> None:
    for user_id, counter in progress.items():
        await db.execute(
            "INSERT INTO daily_progress (user_id, month, counter) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, month) DO UPDATE SET counter = excluded.counter",
            (str(user_id), month, int(counter)),
        )


async def load_claims_for_day(db: Database, day: str) -> list[str]:
    rows = await db.fetchall(
        "SELECT user_id FROM daily_claims WHERE day = ?",
        (day,),
    )
    return [str(row["user_id"]) for row in rows]


async def save_claims_for_day(db: Database, day: str, user_ids: list[str]) -> None:
    for user_id in user_ids:
        await db.execute(
            "INSERT OR IGNORE INTO daily_claims (user_id, day) VALUES (?, ?)",
            (str(user_id), day),
        )


async def build_mutate_snapshot(db: Database, today_str: str) -> dict[str, Any]:
    current_month = await get_current_month(db)
    data: dict[str, Any] = {
        "current_month": current_month,
        "user_progress": await load_user_progress(db, current_month) if current_month else {},
    }
    claims = await load_claims_for_day(db, today_str)
    if claims:
        data[today_str] = claims
    return data


async def persist_mutate_snapshot(db: Database, data: dict[str, Any], today_str: str) -> None:
    current_month = str(data.get("current_month", ""))
    await set_current_month(db, current_month)
    progress = data.get("user_progress", {})
    if current_month and isinstance(progress, dict):
        await save_user_progress(db, current_month, progress)
    claims = data.get(today_str, [])
    if isinstance(claims, list):
        await save_claims_for_day(db, today_str, claims)
