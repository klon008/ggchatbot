"""Admin override state for !кража schedule."""

from __future__ import annotations

from typing import Any, Optional

from .connection import Database

_UNSET = object()


async def ensure_meta(db: Database) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO steal_meta "
        "(id, override_enabled, override_until, last_schedule_open_key) "
        "VALUES (1, 0, NULL, '')"
    )


async def get_meta(db: Database) -> dict[str, Any]:
    await ensure_meta(db)
    row = await db.fetchone(
        "SELECT override_enabled, override_until, last_schedule_open_key "
        "FROM steal_meta WHERE id = 1"
    )
    if row is None:
        return {
            "override_enabled": False,
            "override_until": None,
            "last_schedule_open_key": "",
        }
    until = row["override_until"]
    return {
        "override_enabled": bool(row["override_enabled"]),
        "override_until": float(until) if until is not None else None,
        "last_schedule_open_key": str(row["last_schedule_open_key"] or ""),
    }


async def set_meta(
    db: Database,
    *,
    override_enabled: Optional[bool] = None,
    override_until: Any = _UNSET,
    last_schedule_open_key: Optional[str] = None,
) -> dict[str, Any]:
    """Update steal_meta fields. Pass override_until=None to clear the timer."""
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

    await db.execute(
        "UPDATE steal_meta SET override_enabled = ?, override_until = ?, "
        "last_schedule_open_key = ? WHERE id = 1",
        (
            1 if meta["override_enabled"] else 0,
            meta["override_until"],
            meta["last_schedule_open_key"],
        ),
    )
    return meta
