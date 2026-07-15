"""Migration 016: серия «Классический набор» + 30 карт + бустер/тираж."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from .m009_elsa_mythic import portrait_path

VERSION = 16
DESCRIPTION = "Серия classic: Классический набор, рубашка, 30 карт, бустер+тираж"

_SERIES_ID = "classic"
_SERIES_NAME = "Классический набор"
_CARD_BACK_ID = "card-back-classic"
_BOOSTER_ID = "classic"
_BOOSTER_NAME = "Классический набор"
_DRAW_ID = "draw-classic-001"
_DRAW_NAME = "Тираж № 001"

# (id, name, rarity, sort_order) — порядок как на сайте (classic-* в cardCatalog)
_CATALOG: list[tuple[str, str, str, int]] = [
    ("classic-flounder", "Флаундер", "common", 0),
    ("classic-cinderella", "Золушка", "common", 1),
    ("classic-sebastian", "Себастьян", "common", 2),
    ("classic-asha", "Аша", "common", 3),
    ("classic-pascal", "Паскаль", "common", 4),
    ("classic-jasmine", "Жасмин", "common", 5),
    ("classic-mulan", "Мулан", "common", 6),
    ("classic-tinker-bell", "Динь-Динь", "common", 7),
    ("classic-pocahontas", "Покахонтас", "common", 8),
    ("classic-merida", "Мерида", "common", 9),
    ("classic-mirabel", "Мирабель", "uncommon", 10),
    ("classic-belle", "Белль", "uncommon", 11),
    ("classic-maximus", "Максимус", "uncommon", 12),
    ("classic-olaf", "Олаф", "uncommon", 13),
    ("classic-megara", "Мегара", "uncommon", 14),
    ("classic-raya", "Райя", "uncommon", 15),
    ("classic-moana", "Моана", "uncommon", 16),
    ("classic-tiana", "Тиана", "uncommon", 17),
    ("classic-snow-white", "Белоснежка", "rare", 18),
    ("classic-nokk", "Нокк", "rare", 19),
    ("classic-ariel", "Ариэль", "rare", 20),
    ("classic-rapunzel", "Рапунцель", "rare", 21),
    ("classic-esmeralda", "Эсмеральда", "rare", 22),
    ("classic-elsa", "Эльза", "epic", 23),
    ("classic-aurora", "Аврора", "epic", 24),
    ("classic-kida", "Кида", "epic", 25),
    ("classic-jane", "Джейн", "epic", 26),
    ("classic-anna", "Анна", "legendary", 27),
    ("classic-bruni", "Бруни", "legendary", 28),
    ("classic-elsa-spirit", "Домашняя Эльза", "mythic", 29),
]

_DEFAULT_WEIGHTS = {
    "common": 48.0,
    "uncommon": 24.0,
    "rare": 12.0,
    "epic": 7.0,
    "legendary": 5.0,
    "mythic": 1.0,
    "secretRare": 1.0,
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def upgrade(conn: aiosqlite.Connection) -> None:
    # Fix display name in first series (site: Райя)
    await conn.execute(
        "UPDATE cards SET name = ? WHERE id = ?",
        ("Райя", "raya"),
    )

    await conn.execute(
        """
        INSERT INTO card_series (id, name, sort_order, card_back_id)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            sort_order = excluded.sort_order,
            card_back_id = excluded.card_back_id
        """,
        (_SERIES_ID, _SERIES_NAME, _CARD_BACK_ID),
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
        VALUES (?, ?, NULL, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name
        """,
        (_BOOSTER_ID, _BOOSTER_NAME, now),
    )

    for card_id, _, _, _ in _CATALOG:
        await conn.execute(
            """
            INSERT OR IGNORE INTO booster_pool (booster_id, card_id)
            VALUES (?, ?)
            """,
            (_BOOSTER_ID, card_id),
        )

    # queued — не трогает активный draw001; активируется в админке
    await conn.execute(
        """
        INSERT INTO draws (
            id, booster_id, name, cost_points, cards_per_open,
            rarity_weights, status, daily_limit, created_at
        ) VALUES (?, ?, ?, 15000, 6, ?, 'queued', 0, ?)
        ON CONFLICT(id) DO UPDATE SET
            booster_id = excluded.booster_id,
            name = excluded.name,
            cost_points = excluded.cost_points,
            cards_per_open = excluded.cards_per_open,
            rarity_weights = excluded.rarity_weights
        """,
        (
            _DRAW_ID,
            _BOOSTER_ID,
            _DRAW_NAME,
            json.dumps(_DEFAULT_WEIGHTS, ensure_ascii=False),
            now,
        ),
    )
