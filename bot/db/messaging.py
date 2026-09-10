"""CRUD авто-ответов (auto_responses) и сообщений по таймеру (timed_messages)."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any, Optional

from .connection import Database


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_auto(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "command": str(row["command"]),
        "reply": str(row["reply"]),
        "enabled": bool(row["enabled"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _row_to_timed(row: Any) -> dict[str, Any]:
    next_send_at = row["next_send_at"]
    last_sent_at = row["last_sent_at"]
    return {
        "id": int(row["id"]),
        "text": str(row["text"]),
        "interval_sec": int(row["interval_sec"]),
        "enabled": bool(row["enabled"]),
        "next_send_at": float(next_send_at) if next_send_at is not None else None,
        "last_sent_at": float(last_sent_at) if last_sent_at is not None else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


# --- Авто-ответы -------------------------------------------------------------


async def list_auto_responses(db: Database) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        "SELECT * FROM auto_responses ORDER BY id ASC",
    )
    return [_row_to_auto(row) for row in rows]


async def list_enabled_auto_responses(db: Database) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        "SELECT * FROM auto_responses WHERE enabled = 1 ORDER BY id ASC",
    )
    return [_row_to_auto(row) for row in rows]


async def get_auto_response(db: Database, response_id: int) -> Optional[dict[str, Any]]:
    row = await db.fetchone(
        "SELECT * FROM auto_responses WHERE id = ?",
        (response_id,),
    )
    return _row_to_auto(row) if row else None


async def get_auto_response_by_command(
    db: Database, command: str
) -> Optional[dict[str, Any]]:
    row = await db.fetchone(
        "SELECT * FROM auto_responses WHERE command = ?",
        (command,),
    )
    return _row_to_auto(row) if row else None


async def create_auto_response(
    db: Database,
    command: str,
    reply: str,
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    now = _now_iso()
    cursor = await db.execute(
        "INSERT INTO auto_responses (command, reply, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (command, reply, 1 if enabled else 0, now, now),
    )
    response_id = int(cursor.lastrowid)
    item = await get_auto_response(db, response_id)
    assert item is not None
    return item


async def update_auto_response(
    db: Database,
    response_id: int,
    *,
    command: Optional[str] = None,
    reply: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    sets: list[str] = []
    params: list[Any] = []
    if command is not None:
        sets.append("command = ?")
        params.append(command)
    if reply is not None:
        sets.append("reply = ?")
        params.append(reply)
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if enabled else 0)
    if not sets:
        return await get_auto_response(db, response_id)
    sets.append("updated_at = ?")
    params.append(_now_iso())
    params.append(response_id)
    await db.execute(
        f"UPDATE auto_responses SET {', '.join(sets)} WHERE id = ?",
        tuple(params),
    )
    return await get_auto_response(db, response_id)


async def delete_auto_response(db: Database, response_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM auto_responses WHERE id = ?",
        (response_id,),
    )
    return cursor.rowcount > 0


# --- Сообщения по таймеру ----------------------------------------------------


async def list_timed_messages(db: Database) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        "SELECT * FROM timed_messages ORDER BY id ASC",
    )
    return [_row_to_timed(row) for row in rows]


async def list_enabled_timed_messages(db: Database) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        "SELECT * FROM timed_messages WHERE enabled = 1 ORDER BY next_send_at ASC, id ASC",
    )
    return [_row_to_timed(row) for row in rows]


async def get_timed_message(db: Database, message_id: int) -> Optional[dict[str, Any]]:
    row = await db.fetchone(
        "SELECT * FROM timed_messages WHERE id = ?",
        (message_id,),
    )
    return _row_to_timed(row) if row else None


async def create_timed_message(
    db: Database,
    text: str,
    interval_sec: int,
    *,
    enabled: bool = True,
    next_send_at: Optional[float] = None,
) -> dict[str, Any]:
    now = _now_iso()
    if next_send_at is None:
        next_send_at = time.time() + interval_sec
    cursor = await db.execute(
        "INSERT INTO timed_messages "
        "(text, interval_sec, enabled, next_send_at, last_sent_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, NULL, ?, ?)",
        (text, interval_sec, 1 if enabled else 0, float(next_send_at), now, now),
    )
    message_id = int(cursor.lastrowid)
    item = await get_timed_message(db, message_id)
    assert item is not None
    return item


async def update_timed_message(
    db: Database,
    message_id: int,
    *,
    text: Optional[str] = None,
    interval_sec: Optional[int] = None,
    enabled: Optional[bool] = None,
) -> Optional[dict[str, Any]]:
    sets: list[str] = []
    params: list[Any] = []
    if text is not None:
        sets.append("text = ?")
        params.append(text)
    if interval_sec is not None:
        sets.append("interval_sec = ?")
        params.append(int(interval_sec))
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if enabled else 0)
    if not sets:
        return await get_timed_message(db, message_id)
    sets.append("updated_at = ?")
    params.append(_now_iso())
    params.append(message_id)
    await db.execute(
        f"UPDATE timed_messages SET {', '.join(sets)} WHERE id = ?",
        tuple(params),
    )
    return await get_timed_message(db, message_id)


async def set_timed_schedule(
    db: Database,
    message_id: int,
    *,
    next_send_at: float,
    last_sent_at: Optional[float] = None,
) -> None:
    if last_sent_at is None:
        await db.execute(
            "UPDATE timed_messages SET next_send_at = ?, updated_at = ? WHERE id = ?",
            (float(next_send_at), _now_iso(), message_id),
        )
    else:
        await db.execute(
            "UPDATE timed_messages SET next_send_at = ?, last_sent_at = ?, updated_at = ? "
            "WHERE id = ?",
            (float(next_send_at), float(last_sent_at), _now_iso(), message_id),
        )


async def delete_timed_message(db: Database, message_id: int) -> bool:
    cursor = await db.execute(
        "DELETE FROM timed_messages WHERE id = ?",
        (message_id,),
    )
    return cursor.rowcount > 0
