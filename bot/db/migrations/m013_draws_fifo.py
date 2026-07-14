"""Migration 013: тиражи FIFO — queued / closed вместо inactive."""

from __future__ import annotations

import aiosqlite

VERSION = 13
DESCRIPTION = "Тиражи: inactive → closed; статусы очереди FIFO"


async def upgrade(conn: aiosqlite.Connection) -> None:
    # Старые inactive — уже «снятые» или просто ждущие; запрещаем реактивацию:
    # все inactive → closed. Новые ожидающие создаются как queued.
    await conn.execute(
        "UPDATE draws SET status = 'closed' WHERE status = 'inactive'"
    )
