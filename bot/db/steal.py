"""Steal statistics and atomic steal execution."""

from __future__ import annotations

from typing import Any

from .connection import Database

DEFAULT_INFO: dict[str, Any] = {
    "attempts": 0,
    "success": 0,
    "stolen_total": 0,
    "chance": 5,
    "last_time": 0.0,
    "times_in_jail": 0,
    "last_steal_day_key": "",
}

_INSERT_DEFAULTS = (
    "INSERT OR IGNORE INTO steal_stats "
    "(user_id, attempts, success, stolen_total, chance, last_time, times_in_jail, "
    "last_steal_day_key) "
    "VALUES (?, 0, 0, 0, 5, 0, 0, '')"
)


async def ensure_user(db: Database, user_id: str) -> None:
    uid = str(user_id)
    await db.execute(_INSERT_DEFAULTS, (uid,))


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
        "last_steal_day_key": str(row["last_steal_day_key"] or ""),
    }


async def save_info(db: Database, user_id: str, info: dict[str, Any]) -> None:
    uid = str(user_id)
    await ensure_user(db, uid)
    await db.execute(
        "UPDATE steal_stats SET "
        "attempts = ?, success = ?, stolen_total = ?, chance = ?, "
        "last_time = ?, times_in_jail = ?, last_steal_day_key = ? "
        "WHERE user_id = ?",
        (
            int(info.get("attempts", 0)),
            int(info.get("success", 0)),
            int(info.get("stolen_total", 0)),
            int(info.get("chance", 5)),
            float(info.get("last_time", 0)),
            int(info.get("times_in_jail", 0)),
            str(info.get("last_steal_day_key") or ""),
            uid,
        ),
    )


async def record_steal_success(db: Database, thief_id: str, amount: int) -> None:
    """Update thief steal stats after a successful steal (points handled separately)."""
    thief = str(thief_id)
    async with db.transaction() as conn:
        await conn.execute(_INSERT_DEFAULTS, (thief,))
        await conn.execute(
            "UPDATE steal_stats SET "
            "success = success + 1, stolen_total = stolen_total + ? "
            "WHERE user_id = ?",
            (amount, thief),
        )


async def record_steal_reverted(db: Database, thief_id: str, amount: int) -> None:
    """Undo stolen_total after prison return. success is not rolled back."""
    thief = str(thief_id)
    await ensure_user(db, thief)
    await db.execute(
        "UPDATE steal_stats SET "
        "stolen_total = CASE WHEN stolen_total > ? THEN stolen_total - ? ELSE 0 END "
        "WHERE user_id = ?",
        (amount, amount, thief),
    )


async def increment_jail_count(db: Database, user_id: str) -> None:
    uid = str(user_id)
    await ensure_user(db, uid)
    await db.execute(
        "UPDATE steal_stats SET times_in_jail = times_in_jail + 1 WHERE user_id = ?",
        (uid,),
    )


async def list_all_stats(db: Database) -> list[dict[str, Any]]:
    """All steal_stats joined with user_names, sorted by chance then stolen_total."""
    rows = await db.fetchall(
        "SELECT s.user_id, COALESCE(u.user_name, '') AS user_name, "
        "s.attempts, s.success, s.stolen_total, s.chance, s.times_in_jail, "
        "s.last_steal_day_key, s.last_time "
        "FROM steal_stats s "
        "LEFT JOIN user_names u ON u.user_id = s.user_id "
        "ORDER BY s.chance DESC, s.stolen_total DESC, s.attempts DESC"
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "user_id": str(row["user_id"]),
                "user_name": str(row["user_name"] or ""),
                "attempts": int(row["attempts"]),
                "success": int(row["success"]),
                "stolen_total": int(row["stolen_total"]),
                "chance": int(row["chance"]),
                "times_in_jail": int(row["times_in_jail"]),
                "last_steal_day_key": str(row["last_steal_day_key"] or ""),
                "last_time": float(row["last_time"] or 0),
            }
        )
    return out


async def list_all_infos_for_decay(db: Database) -> list[tuple[str, dict[str, Any]]]:
    """(user_id, info) for missed-day decay pass."""
    rows = await db.fetchall(
        "SELECT user_id, attempts, success, stolen_total, chance, last_time, "
        "times_in_jail, last_steal_day_key FROM steal_stats"
    )
    result: list[tuple[str, dict[str, Any]]] = []
    for row in rows:
        uid = str(row["user_id"])
        result.append(
            (
                uid,
                {
                    "attempts": int(row["attempts"]),
                    "success": int(row["success"]),
                    "stolen_total": int(row["stolen_total"]),
                    "chance": int(row["chance"]),
                    "last_time": float(row["last_time"]),
                    "times_in_jail": int(row["times_in_jail"]),
                    "last_steal_day_key": str(row["last_steal_day_key"] or ""),
                },
            )
        )
    return result
