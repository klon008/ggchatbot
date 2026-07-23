"""Migration 020: серия «Пляжный сезон» + карты + бустер/тираж (series-pack-web)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from .m009_elsa_mythic import portrait_path

VERSION = 20
DESCRIPTION = "Серия summer-2026: Пляжный сезон, рубашка, карты, бустер+тираж"

_SERIES_ID = "summer-2026"
_SERIES_NAME = "Пляжный сезон"
_CARD_BACK_ID = "card-back-summer-2026"
_SERIES_SORT = 1
_BOOSTER_ID = "resort-2026"
_BOOSTER_NAME = "Пляжный сезон"
_PROMO_URL = None
_DRAW_ID = "draw-summer-2026-001"
_DRAW_NAME = "Тираж № 005"
_DRAW_STATUS = "queued"
_COST = 8000
_CARDS_PER_OPEN = 6
_DAILY_LIMIT = 0

_CATALOG: list[tuple[str, str, str, int]] = [
    ("resort-aurora", "Пляжная Аврора", "rare", 0),
    ("resort-alisa", "Пляжная Алиса", "uncommon", 1),
    ("resort-anna", "Пляжная Анна", "epic", 2),
    ("resort-ariel", "Пляжная Ариэль", "uncommon", 3),
    ("resort-belle", "Пляжная Белль", "uncommon", 4),
    ("resort-snow-white", "Пляжная Белоснежка", "common", 5),
    ("resort-vanellope", "Пляжная Ванилопа", "rare", 6),
    ("resort-jane", "Пляжная Джейн", "uncommon", 7),
    ("resort-jasmine", "Пляжная Жасмин", "uncommon", 8),
    ("resort-cinderella", "Пляжная Золушка", "rare", 9),
    ("resort-cassandra", "Пляжная Кассандра", "epic", 10),
    ("resort-kida", "Пляжная Кида", "rare", 11),
    ("resort-megara", "Пляжная Мегара", "rare", 12),
    ("resort-merida", "Пляжная Мерида", "uncommon", 13),
    ("resort-mirabel", "Пляжная Мирабель", "common", 14),
    ("resort-moana", "Пляжная Моана", "uncommon", 15),
    ("resort-mulan", "Пляжная Мулан", "common", 16),
    ("resort-nani", "Пляжная Нани", "common", 17),
    ("resort-olaf", "Пляжный Олаф", "common", 18),
    ("resort-pocahontas", "Пляжная Покахонтас", "legendary", 19),
    ("resort-rapunzel", "Пляжная Рапунцель", "epic", 20),
    ("resort-sebastian", "Пляжный Себастьян", "common", 21),
    ("resort-tiana", "Пляжная Тиана", "common", 22),
    ("resort-honey-lemon", "Пляжная Хани Лемон", "epic", 23),
    ("resort-elsa", "Пляжная Эльза", "legendary", 24),
    ("resort-chilling-elsa", "Уставшая Эльза", "mythic", 25),
    ("resort-esmeralda", "Пляжная Эсмеральда", "common", 26),
]

_WEIGHTS = {
    "common": 48.1,
    "uncommon": 24.2,
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
