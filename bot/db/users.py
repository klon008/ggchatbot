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


async def list_user_ids_with_names(db: Database) -> list[str]:
    rows = await db.fetchall(
        "SELECT user_id FROM user_names WHERE user_name != ''"
    )
    return [row["user_id"] for row in rows]


async def sync_online_users(db: Database, users: list[dict]) -> tuple[int, int]:
    """Upsert nicks for online GG users. Returns (updated, total_online_with_name)."""
    updated = 0
    total = 0
    for user in users:
        uid = str(user.get("id", ""))
        if not uid or uid == "0":
            continue
        name = str(user.get("name", "")).strip()
        if not name:
            continue
        total += 1
        await touch_user_name(db, uid, name)
        updated += 1
    return updated, total
