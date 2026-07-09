"""Song request queue persistence."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Optional

from .connection import Database


def _track_from_row(row) -> dict[str, Any]:
    return {
        "video_id": row["video_id"],
        "requested_by": row["requested_by"],
        "requested_by_name": row["requested_by_name"],
        "url": row["url"],
        "title": row["title"],
        "added_at": float(row["added_at"]),
    }


async def load_meta(db: Database) -> tuple[Optional[dict], Optional[str], int]:
    row = await db.fetchone(
        "SELECT current_json, current_token, token_counter FROM queue_meta WHERE id = 1"
    )
    if row is None:
        return None, None, 1
    current = json.loads(row["current_json"]) if row["current_json"] else None
    token = row["current_token"]
    counter = int(row["token_counter"])
    return current, token, counter


async def save_meta(
    db: Database,
    current: Optional[dict],
    token: Optional[str],
    token_counter: int,
) -> None:
    current_json = json.dumps(current, ensure_ascii=False) if current else None
    await db.execute(
        "UPDATE queue_meta SET current_json = ?, current_token = ?, token_counter = ? WHERE id = 1",
        (current_json, token, token_counter),
    )


async def load_items(db: Database) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        "SELECT video_id, requested_by, requested_by_name, url, title, added_at "
        "FROM queue_items ORDER BY position ASC"
    )
    return [_track_from_row(row) for row in rows]


async def replace_items(db: Database, items: list[dict[str, Any]]) -> None:
    async with db.transaction() as conn:
        await conn.execute("DELETE FROM queue_items")
        for pos, item in enumerate(items):
            await conn.execute(
                "INSERT INTO queue_items "
                "(position, video_id, requested_by, requested_by_name, url, title, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    pos,
                    item["video_id"],
                    item["requested_by"],
                    item.get("requested_by_name", ""),
                    item["url"],
                    item.get("title", ""),
                    float(item.get("added_at", 0)),
                ),
            )


async def persist_queue(
    db: Database,
    queue_items: list[dict[str, Any]],
    current: Optional[dict],
    token: Optional[str],
    token_counter: int,
) -> None:
    async with db.transaction() as conn:
        await conn.execute("DELETE FROM queue_items")
        for pos, item in enumerate(queue_items):
            await conn.execute(
                "INSERT INTO queue_items "
                "(position, video_id, requested_by, requested_by_name, url, title, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    pos,
                    item["video_id"],
                    item["requested_by"],
                    item.get("requested_by_name", ""),
                    item["url"],
                    item.get("title", ""),
                    float(item.get("added_at", 0)),
                ),
            )
        current_json = json.dumps(current, ensure_ascii=False) if current else None
        await conn.execute(
            "UPDATE queue_meta SET current_json = ?, current_token = ?, token_counter = ? WHERE id = 1",
            (current_json, token, token_counter),
        )


def track_to_dict(track) -> dict[str, Any]:
    return asdict(track)
