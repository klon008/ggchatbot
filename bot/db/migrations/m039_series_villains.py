"""Migration 039: серия «Антигерой» + карты + бустер/тираж (series-pack-web)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from .m009_elsa_mythic import portrait_path

VERSION = 39
DESCRIPTION = "Серия villains: Антигерой, рубашка, карты, бустер+тираж"

_SERIES_ID = "villains"
_SERIES_NAME = "Антигерой"
_CARD_BACK_ID = "card-back-villains"
_SERIES_SORT = 1
_BOOSTER_ID = "villains"
_BOOSTER_NAME = "Антигерой"
_PROMO_URL = None
_DRAW_ID = "draw-villains-001"
_DRAW_NAME = "Тираж № 007"
_DRAW_STATUS = "queued"
_COST = 8000
_CARDS_PER_OPEN = 6
_DAILY_LIMIT = 0

_CATALOG: list[tuple[str, str, str, int]] = [
    ("shan_yu", "Шань-Ю", "mythic", 0),
    ("aid", "Аид", "epic", 1),
    ("gaston", "Гастон", "rare", 2),
    ("gothel", "Матушка Готель", "common", 3),
    ("jafar", "Джафар", "common", 4),
    ("evil_queen", "Злая королева", "uncommon", 5),
    ("yzma", "Изма", "rare", 6),
    ("john_clayton", "Джон Клейтон", "common", 7),
    ("captain_hook", "Капитан Крюк", "uncommon", 8),
    ("maleficent", "Малефисента", "common", 9),
    ("lyle_tiberius_rourke", "Лайл Тиберий Рурк", "uncommon", 10),
    ("john_silver", "Джон Сильвер", "rare", 11),
    ("syndrome", "Бадди «Синдром» Пайн", "legendary", 12),
    ("cruella_de_vil", "Стервелла Де Виль", "legendary", 13),
    ("lady_tremaine", "Леди Тремейн", "uncommon", 14),
    ("ursula", "Урсула", "uncommon", 15),
    ("doctor_facilier", "Доктор Фасилье", "common", 16),
    ("claude_frollo", "Клод Фролло", "epic", 17),
    ("prince_hans", "Принц Ханс", "epic", 18),
    ("queen_of_hearts", "Червонная королева", "common", 19),
]

_WEIGHTS = {
    "common": 48.0,
    "uncommon": 24.0,
    "rare": 13.0,
    "epic": 4.5,
    "legendary": 2.6,
    "mythic": 0.7,
    "secretRare": 0.0
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO card_series (id, name, sort_order, card_back_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            sort_order = excluded.sort_order,
            card_back_id = excluded.card_back_id
        """,
        (_SERIES_ID, _SERIES_NAME, _SERIES_SORT, _CARD_BACK_ID),
    )

    for card_id, name, rarity, sort_order in _CATALOG:
        await conn.execute(
            """
            INSERT INTO cards (id, series_id, name, rarity, sort_order, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                series_id = excluded.series_id,
                name = excluded.name,
                rarity = excluded.rarity,
                sort_order = excluded.sort_order,
                image_url = excluded.image_url
            """,
            (
                card_id,
                _SERIES_ID,
                name,
                rarity,
                sort_order,
                portrait_path(card_id),
            ),
        )

    now = _utcnow_iso()
    await conn.execute(
        """
        INSERT INTO boosters (id, name, promo_image_url, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            promo_image_url = excluded.promo_image_url
        """,
        (_BOOSTER_ID, _BOOSTER_NAME, _PROMO_URL, now),
    )

    for card_id, _, _, _ in _CATALOG:
        await conn.execute(
            """
            INSERT OR IGNORE INTO booster_pool (booster_id, card_id)
            VALUES (?, ?)
            """,
            (_BOOSTER_ID, card_id),
        )

    await conn.execute(
        """
        INSERT INTO draws (
            id, booster_id, name, cost_points, cards_per_open,
            rarity_weights, status, daily_limit, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            booster_id = excluded.booster_id,
            name = excluded.name,
            cost_points = excluded.cost_points,
            cards_per_open = excluded.cards_per_open,
            rarity_weights = excluded.rarity_weights,
            daily_limit = excluded.daily_limit
        """,
        (
            _DRAW_ID,
            _BOOSTER_ID,
            _DRAW_NAME,
            _COST,
            _CARDS_PER_OPEN,
            json.dumps(_WEIGHTS, ensure_ascii=False),
            _DRAW_STATUS,
            _DAILY_LIMIT,
            now,
        ),
    )
