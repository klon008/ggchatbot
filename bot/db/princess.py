"""CRUD для ивентов принцесс (расписание + ручные гранты до конца суток)."""

from __future__ import annotations

import json
from typing import Any, Optional

from bot.db.connection import Database

KIND_VIEW = "view"
KIND_MESSAGE = "message"
GRANT_KINDS = (KIND_VIEW, KIND_MESSAGE)


async def ensure_meta(db: Database) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO princess_meta (id, events_json) VALUES (1, '')"
    )


async def get_meta(db: Database) -> dict[str, Any]:
    await ensure_meta(db)
    row = await db.fetchone(
        "SELECT events_json FROM princess_meta WHERE id = 1"
    )
    assert row is not None
    return {"events_json": str(row[0] or "")}


async def set_meta(db: Database, *, events_json: Optional[str] = None) -> None:
    await ensure_meta(db)
    meta = await get_meta(db)
    if events_json is not None:
        meta["events_json"] = events_json
    await db.execute(
        "UPDATE princess_meta SET events_json = ? WHERE id = 1",
        (meta["events_json"],),
    )


def parse_events_json(raw: str) -> Optional[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


async def get_events_override(db: Database) -> Optional[dict[str, Any]]:
    meta = await get_meta(db)
    return parse_events_json(meta.get("events_json", ""))


async def set_events_override(db: Database, payload: Optional[dict[str, Any]]) -> None:
    if payload is None:
        await set_meta(db, events_json="")
        return
    await set_meta(db, events_json=json.dumps(payload, ensure_ascii=False))


async def has_grant(db: Database, user_id: str, kind: str, day_key: str) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM princess_bonus_grants "
        "WHERE user_id = ? AND kind = ? AND day_key = ?",
        (str(user_id), str(kind), str(day_key)),
    )
    return row is not None


async def list_grant_user_ids(
    db: Database, *, kind: str, day_key: str
) -> set[str]:
    rows = await db.fetchall(
        "SELECT user_id FROM princess_bonus_grants WHERE kind = ? AND day_key = ?",
        (str(kind), str(day_key)),
    )
    return {str(r[0]) for r in rows}


async def upsert_grant(
    db: Database, *, user_id: str, kind: str, day_key: str
) -> None:
    kind_key = str(kind)
    if kind_key not in GRANT_KINDS:
        raise ValueError("kind")
    await db.execute(
        """
        INSERT INTO princess_bonus_grants (user_id, kind, day_key)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, kind) DO UPDATE SET day_key = excluded.day_key
        """,
        (str(user_id), kind_key, str(day_key)),
    )
