"""Versioned database migrations (applied by bot/db/migrate.py)."""

from __future__ import annotations

from typing import Protocol

import aiosqlite

from . import (
    m002_paid_cost,
    m003_orders_enabled,
    m004_user_names,
    m005_roulette,
    m006_minigames_bank,
    m007_races,
    m008_cards,
    m009_elsa_mythic,
    m010_card_asset_urls,
    m011_series_card_back,
    m012_cards_enabled,
    m013_draws_fifo,
    m014_anim_speed,
    m015_draw001_cost,
    m016_classic_series,
    m017_polls,
    m018_fishing,
)


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
    m008_cards,
    m009_elsa_mythic,
    m010_card_asset_urls,
    m011_series_card_back,
    m012_cards_enabled,
    m013_draws_fifo,
    m014_anim_speed,
    m015_draw001_cost,
    m016_classic_series,
    m017_polls,
    m018_fishing,
]
