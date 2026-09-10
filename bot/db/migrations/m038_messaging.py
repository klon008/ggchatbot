"""Migration 038: auto_responses + timed_messages (авто-ответы и таймер-сообщения)."""

from __future__ import annotations

import aiosqlite

VERSION = 38
DESCRIPTION = (
    "таблицы auto_responses (авто-ответы на !команды) "
    "и timed_messages (сообщения по таймеру)"
)


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auto_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            reply TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_auto_responses_command
        ON auto_responses(command)
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS timed_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            interval_sec INTEGER NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            next_send_at REAL,
            last_sent_at REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
