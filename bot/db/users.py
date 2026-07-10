"""Display names for chat users (user_id -> user_name)."""

from __future__ import annotations

from .connection import Database


async def touch_user_name(db: Database, user_id: str, user_name: str) -> None:
    name = str(user_name).strip()
    if not name:
        return
    uid = str(user_id)
    await db.execute(
        "INSERT INTO user_names (user_id, user_name) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET user_name = excluded.user_name",
        (uid, name),
    )


async def get_user_name(db: Database, user_id: str) -> str:
    row = await db.fetchone(
        "SELECT user_name FROM user_names WHERE user_id = ?",
        (str(user_id),),
    )
    return str(row["user_name"]) if row else ""
