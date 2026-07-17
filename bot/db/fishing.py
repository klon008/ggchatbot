"""CRUD для модуля рыбалки."""

from __future__ import annotations

from typing import Any, Optional

from bot.db.connection import Database

ROD_NONE = "none"
ROD_OK = "ok"
ROD_BROKEN = "broken"


async def ensure_meta(db: Database) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO fishing_meta "
        "(id, day_key, first_fish_claimed, current_week_id, pending_rewards_week_id) "
        "VALUES (1, '', 0, '', '')"
    )


async def get_meta(db: Database) -> dict[str, Any]:
    await ensure_meta(db)
    row = await db.fetchone(
        "SELECT day_key, first_fish_claimed, current_week_id, pending_rewards_week_id "
        "FROM fishing_meta WHERE id = 1"
    )
    assert row is not None
    return {
        "day_key": str(row[0] or ""),
        "first_fish_claimed": bool(row[1]),
        "current_week_id": str(row[2] or ""),
        "pending_rewards_week_id": str(row[3] or ""),
    }


async def set_meta(
    db: Database,
    *,
    day_key: Optional[str] = None,
    first_fish_claimed: Optional[bool] = None,
    current_week_id: Optional[str] = None,
    pending_rewards_week_id: Optional[str] = None,
) -> None:
    await ensure_meta(db)
    meta = await get_meta(db)
    if day_key is not None:
        meta["day_key"] = day_key
    if first_fish_claimed is not None:
        meta["first_fish_claimed"] = first_fish_claimed
    if current_week_id is not None:
        meta["current_week_id"] = current_week_id
    if pending_rewards_week_id is not None:
        meta["pending_rewards_week_id"] = pending_rewards_week_id
    await db.execute(
        "UPDATE fishing_meta SET day_key = ?, first_fish_claimed = ?, "
        "current_week_id = ?, pending_rewards_week_id = ? WHERE id = 1",
        (
            meta["day_key"],
            1 if meta["first_fish_claimed"] else 0,
            meta["current_week_id"],
            meta["pending_rewards_week_id"],
        ),
    )


async def get_player(db: Database, user_id: str) -> Optional[dict[str, Any]]:
    row = await db.fetchone(
        "SELECT user_id, user_name, energy, energy_updated_at, worms, maggots, "
        "rod_state, last_cast_at, day_key FROM fishing_players WHERE user_id = ?",
        (str(user_id),),
    )
    if row is None:
        return None
    return _player_row(row)


async def upsert_player(db: Database, player: dict[str, Any]) -> None:
    await db.execute(
        """
        INSERT INTO fishing_players (
            user_id, user_name, energy, energy_updated_at, worms, maggots,
            rod_state, last_cast_at, day_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            user_name = excluded.user_name,
            energy = excluded.energy,
            energy_updated_at = excluded.energy_updated_at,
            worms = excluded.worms,
            maggots = excluded.maggots,
            rod_state = excluded.rod_state,
            last_cast_at = excluded.last_cast_at,
            day_key = excluded.day_key
        """,
        (
            str(player["user_id"]),
            str(player.get("user_name") or ""),
            int(player["energy"]),
            float(player["energy_updated_at"]),
            int(player["worms"]),
            int(player["maggots"]),
            str(player["rod_state"]),
            float(player["last_cast_at"]),
            str(player.get("day_key") or ""),
        ),
    )


async def reset_all_for_new_day(
    db: Database,
    *,
    energy: int,
    energy_updated_at: float,
    day_key: str,
) -> None:
    await db.execute(
        "UPDATE fishing_players SET energy = ?, energy_updated_at = ?, "
        "worms = 0, maggots = 0, day_key = ?",
        (energy, energy_updated_at, day_key),
    )


async def restore_all_energy(
    db: Database,
    *,
    energy: int,
    energy_updated_at: float,
) -> int:
    cursor = await db.execute(
        "UPDATE fishing_players SET energy = ?, energy_updated_at = ?",
        (energy, energy_updated_at),
    )
    return int(cursor.rowcount or 0)


async def count_players(db: Database) -> int:
    row = await db.fetchone("SELECT COUNT(*) FROM fishing_players")
    return int(row[0]) if row else 0


async def get_record(db: Database, user_id: str, species: str) -> Optional[float]:
    row = await db.fetchone(
        "SELECT weight FROM fishing_records WHERE user_id = ? AND species = ?",
        (str(user_id), species),
    )
    return float(row[0]) if row else None


async def list_records(db: Database, user_id: str) -> list[tuple[str, float]]:
    rows = await db.fetchall(
        "SELECT species, weight FROM fishing_records WHERE user_id = ? ORDER BY species",
        (str(user_id),),
    )
    return [(str(r[0]), float(r[1])) for r in rows]


async def set_record_if_better(
    db: Database,
    user_id: str,
    species: str,
    weight: float,
) -> bool:
    current = await get_record(db, user_id, species)
    if current is not None and weight <= current:
        return False
    await db.execute(
        """
        INSERT INTO fishing_records (user_id, species, weight)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, species) DO UPDATE SET weight = excluded.weight
        """,
        (str(user_id), species, float(weight)),
    )
    return True


async def get_week_weight(
    db: Database,
    week_id: str,
    user_id: str,
    species: str,
) -> Optional[dict[str, Any]]:
    row = await db.fetchone(
        "SELECT weight, achieved_at FROM fishing_week_weights "
        "WHERE week_id = ? AND user_id = ? AND species = ?",
        (week_id, str(user_id), species),
    )
    if row is None:
        return None
    return {"weight": float(row[0]), "achieved_at": float(row[1])}


async def set_week_weight_if_better(
    db: Database,
    *,
    week_id: str,
    user_id: str,
    user_name: str,
    species: str,
    weight: float,
    achieved_at: float,
) -> bool:
    current = await get_week_weight(db, week_id, user_id, species)
    if current is not None and weight <= current["weight"]:
        return False
    await db.execute(
        """
        INSERT INTO fishing_week_weights
            (week_id, user_id, user_name, species, weight, achieved_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(week_id, user_id, species) DO UPDATE SET
            user_name = excluded.user_name,
            weight = excluded.weight,
            achieved_at = excluded.achieved_at
        """,
        (week_id, str(user_id), user_name, species, float(weight), float(achieved_at)),
    )
    return True


async def week_leaders(db: Database, week_id: str) -> list[dict[str, Any]]:
    """Топ-1 по каждому виду: макс. вес, при ничьей — раньше achieved_at."""
    rows = await db.fetchall(
        """
        SELECT w.species, w.user_id, w.user_name, w.weight, w.achieved_at
        FROM fishing_week_weights w
        INNER JOIN (
            SELECT species, MAX(weight) AS max_weight
            FROM fishing_week_weights
            WHERE week_id = ?
            GROUP BY species
        ) m ON w.species = m.species AND w.weight = m.max_weight
        WHERE w.week_id = ?
        ORDER BY w.species, w.achieved_at ASC
        """,
        (week_id, week_id),
    )
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        species = str(row[0])
        if species in best:
            continue
        best[species] = {
            "species": species,
            "user_id": str(row[1]),
            "user_name": str(row[2] or ""),
            "weight": float(row[3]),
            "achieved_at": float(row[4]),
        }
    return list(best.values())


async def week_fish_of_week(db: Database, week_id: str) -> Optional[dict[str, Any]]:
    row = await db.fetchone(
        """
        SELECT species, user_id, user_name, weight, achieved_at
        FROM fishing_week_weights
        WHERE week_id = ?
        ORDER BY weight DESC, achieved_at ASC
        LIMIT 1
        """,
        (week_id,),
    )
    if row is None:
        return None
    return {
        "species": str(row[0]),
        "user_id": str(row[1]),
        "user_name": str(row[2] or ""),
        "weight": float(row[3]),
        "achieved_at": float(row[4]),
    }


def _player_row(row: tuple) -> dict[str, Any]:
    return {
        "user_id": str(row[0]),
        "user_name": str(row[1] or ""),
        "energy": int(row[2]),
        "energy_updated_at": float(row[3]),
        "worms": int(row[4]),
        "maggots": int(row[5]),
        "rod_state": str(row[6] or ROD_NONE),
        "last_cast_at": float(row[7]),
        "day_key": str(row[8] or ""),
    }
