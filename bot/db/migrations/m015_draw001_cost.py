"""Migration 015: боевая цена стартового тиража draw001."""

from __future__ import annotations

import aiosqlite

VERSION = 15
DESCRIPTION = "draws: cost_points=15000 для draw001"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "UPDATE draws SET cost_points = 15000 WHERE id = ?",
        ("draw001",),
    )
