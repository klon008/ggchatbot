"""Migration 037: draw_templates — планы тиражей вне FIFO."""

from __future__ import annotations

import aiosqlite

VERSION = 37
DESCRIPTION = "таблица draw_templates (шаблоны тиражей)"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draw_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            planned_draw_id TEXT NOT NULL DEFAULT '',
            booster_id TEXT NOT NULL,
            cost_points INTEGER NOT NULL,
            cards_per_open INTEGER NOT NULL,
            daily_limit INTEGER NOT NULL DEFAULT 0,
            rarity_weights TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (booster_id) REFERENCES boosters(id)
        )
        """
    )
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_draw_templates_planned_draw_id
        ON draw_templates(planned_draw_id)
        WHERE planned_draw_id != ''
        """
    )
