"""Versioned database migrations (applied by bot/db/migrate.py)."""

from __future__ import annotations

from typing import Protocol

import aiosqlite

from . import m002_paid_cost, m003_orders_enabled, m004_user_names, m005_roulette, m006_minigames_bank, m007_races


class Migration(Protocol):
    VERSION: int
    DESCRIPTION: str

    async def upgrade(self, conn: aiosqlite.Connection) -> None: ...


MIGRATIONS: list[Migration] = [
    m002_paid_cost,
    m003_orders_enabled,
    m004_user_names,
    m005_roulette,
    m006_minigames_bank,
    m007_races,
]
