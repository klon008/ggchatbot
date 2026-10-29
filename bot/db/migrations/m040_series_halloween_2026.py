"""Migration 040: серия «Жуткий и пугающий» + карты + бустер/тираж (series-pack-web)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from .m009_elsa_mythic import portrait_path

VERSION = 40
DESCRIPTION = "Серия halloween_2026: Жуткий и пугающий, рубашка, карты, бустер+тираж"

_SERIES_ID = "halloween_2026"
_SERIES_NAME = "Жуткий и пугающий"
_CARD_BACK_ID = "card-back-halloween_2026"
_SERIES_SORT = 1
_BOOSTER_ID = "halloween_2026"
_BOOSTER_NAME = "Жуткий и пугающий"
_PROMO_URL = None
_DRAW_ID = "draw-halloween_2026-001"
_DRAW_NAME = "Тираж № 008"
_DRAW_STATUS = "queued"
_COST = 8000
_CARDS_PER_OPEN = 6
_DAILY_LIMIT = 0

_CATALOG: list[tuple[str, str, str, int]] = [
    ("li_shang_halloween_2026", "Жуткий Ли Шанг", "rare", 0),
    ("violet_parr_halloween_2026", "Жуткая Виолетта Парр", "common", 1),
    ("vanessa_halloween_2026", "Жуткая Ванесса (Урсула)", "uncommon", 2),
    ("beast_halloween_2026", "Жуткое Чудовище", "uncommon", 3),
    ("helga_sinclair__halloween_2026", "Жуткая Хельга Синклер", "common", 4),
    ("rapunzel__halloween_2026", "Жуткая Рапунцель", "rare", 5),
    ("ariel_halloween_2026", "Жуткая Ариэль", "epic", 6),
    ("ralph__halloween_2026", "Жуткий Ральф", "uncommon", 7),
    ("sharlotte_la_bouff_halloween_2026", "Жуткая Шарлотта Ла Бафф", "epic", 8),
    ("gogo_tomago_halloween_2026", "Жуткая Гого Томаго", "rare", 9),
    ("aladdin_halloween_2026", "Жуткий Аладдин", "common", 10),
    ("bruno_halloween_2026", "Жуткий Бруно", "common", 11),
    ("miguel_halloween_2026", "Жуткий Мигель", "uncommon", 12),
    ("olaf_halloween_2026", "Жуткий Олаф", "rare", 13),
    ("elsa_halloween_2026", "Жуткая Эльза", "legendary", 14),
    ("kida_halloween_2026", "Жуткая Кида", "epic", 15),
    ("snow_white_halloween_2026", "Жуткая Белоснежка", "mythic", 16),
    ("anna_halloween_2026", "Жуткая Анна", "legendary", 17),
    ("kronk_halloween_2026", "Жуткий Кронк", "common", 18),
    ("hunchback_halloween_2026", "Жуткий Горбун", "uncommon", 19),
    ("maui_halloween_2026", "Жуткий Мауи", "common", 20),
    ("fil_halloween_2026", "Жуткий Фил", "uncommon", 21),
]

_WEIGHTS = {
    "common": 48.0,
    "uncommon": 24.0,
    "rare": 13.5,
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
