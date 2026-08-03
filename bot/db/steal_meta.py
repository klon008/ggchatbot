"""Admin override state for !кража schedule and loot tier overrides."""

from __future__ import annotations

import json
from typing import Any, Optional

from .connection import Database

_UNSET = object()


async def ensure_meta(db: Database) -> None:
    # Без новых колонок: на БД до m028 их ещё нет (добавляет миграция).
    await db.execute(
        "INSERT OR IGNORE INTO steal_meta "
        "(id, override_enabled, override_until, last_schedule_open_key) "
        "VALUES (1, 0, NULL, '')"
    )


def _parse_loot_json(raw: Any) -> Optional[dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def get_meta(db: Database) -> dict[str, Any]:
    await ensure_meta(db)
    row = await db.fetchone(
        "SELECT override_enabled, override_until, last_schedule_open_key, "
        "last_miss_decay_day_key, loot_tiers_json "
        "FROM steal_meta WHERE id = 1"
    )
    if row is None:
        return {
            "override_enabled": False,
            "override_until": None,
            "last_schedule_open_key": "",
            "last_miss_decay_day_key": "",
            "loot_tiers": None,
        }
    until = row["override_until"]
    return {
        "override_enabled": bool(row["override_enabled"]),
        "override_until": float(until) if until is not None else None,
        "last_schedule_open_key": str(row["last_schedule_open_key"] or ""),
        "last_miss_decay_day_key": str(row["last_miss_decay_day_key"] or ""),
        "loot_tiers": _parse_loot_json(row["loot_tiers_json"]),
    }


async def set_meta(
    db: Database,
    *,
    override_enabled: Optional[bool] = None,
    override_until: Any = _UNSET,
    last_schedule_open_key: Optional[str] = None,
    last_miss_decay_day_key: Optional[str] = None,
    loot_tiers: Any = _UNSET,
) -> dict[str, Any]:
    """Update steal_meta fields. Pass override_until=None to clear the timer.
    Pass loot_tiers=None to clear override (use settings defaults).
    """
    await ensure_meta(db)
    meta = await get_meta(db)
    if override_enabled is not None:
        meta["override_enabled"] = bool(override_enabled)
    if override_until is not _UNSET:
        meta["override_until"] = (
            float(override_until) if override_until is not None else None
        )
    if last_schedule_open_key is not None:
        meta["last_schedule_open_key"] = str(last_schedule_open_key)
    if last_miss_decay_day_key is not None:
        meta["last_miss_decay_day_key"] = str(last_miss_decay_day_key)
    if loot_tiers is not _UNSET:
        meta["loot_tiers"] = loot_tiers if loot_tiers is not None else None

    loot_json = None
    if meta["loot_tiers"] is not None:
        loot_json = json.dumps(meta["loot_tiers"], ensure_ascii=False)

    await db.execute(
        "UPDATE steal_meta SET override_enabled = ?, override_until = ?, "
        "last_schedule_open_key = ?, last_miss_decay_day_key = ?, "
        "loot_tiers_json = ? WHERE id = 1",
        (
            1 if meta["override_enabled"] else 0,
            meta["override_until"],
            meta["last_schedule_open_key"],
            meta["last_miss_decay_day_key"],
            loot_json,
        ),
    )
    return meta
