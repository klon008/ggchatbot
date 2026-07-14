"""Migration 008: коллекционные карты (серии, бустеры, тиражи, альбомы)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

VERSION = 8
DESCRIPTION = "Таблицы card_series, cards, boosters, booster_pool, draws, user_cards, booster_openings"

_SERIES_ID = "fantast"
_SERIES_NAME = "Фантастический коллекционер"
_BOOSTER_ID = "start"
_BOOSTER_NAME = "Стартовый набор"
_DRAW_ID = "draw001"
_DRAW_NAME = "Тираж № 001"

_CARDS: list[tuple[str, str, str]] = [
    ("cinderella", "Золушка", "common"),
    ("belle", "Белль", "uncommon"),
    ("ariel", "Ариэль", "rare"),
    ("snow-white", "Белоснежка", "common"),
    ("rapunzel", "Рапунцель", "epic"),
    ("jasmine", "Жасмин", "uncommon"),
    ("moana", "Моана", "rare"),
    ("pocahontas", "Покахонтас", "common"),
    ("aurora", "Аврора", "legendary"),
    ("tiana", "Тиана", "uncommon"),
    ("merida", "Мерида", "rare"),
    ("asha", "Аша", "common"),
    ("raya", "Рая", "epic"),
    ("mulan", "Мулан", "uncommon"),
    ("anna", "Анна", "rare"),
    ("nala", "Нала", "common"),
    ("queen-elsa", "Королева Эльза", "secretRare"),
    ("megara", "Мегара", "secretRare"),
    ("esmeralda", "Эсмеральда", "rare"),
    ("jane", "Джейн", "common"),
    ("mirabel", "Мирабель", "epic"),
    ("tinker-bell", "Динь-Динь", "uncommon"),
    ("kida", "Кида", "rare"),
    ("giselle", "Жизель", "uncommon"),
    ("flounder", "Флаундер", "common"),
    ("olaf", "Олаф", "common"),
    ("pascal", "Паскаль", "common"),
]

_DEFAULT_WEIGHTS = {
    "common": 50.0,
    "uncommon": 25.0,
    "rare": 12.0,
    "epic": 7.0,
    "legendary": 5.0,
    "secretRare": 1.0,
}


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS card_series (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            series_id TEXT NOT NULL,
            name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (series_id) REFERENCES card_series(id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS boosters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            promo_image_url TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS booster_pool (
            booster_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            PRIMARY KEY (booster_id, card_id),
            FOREIGN KEY (booster_id) REFERENCES boosters(id),
            FOREIGN KEY (card_id) REFERENCES cards(id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draws (
            id TEXT PRIMARY KEY,
            booster_id TEXT NOT NULL,
            name TEXT NOT NULL,
            cost_points INTEGER NOT NULL,
            cards_per_open INTEGER NOT NULL,
            rarity_weights TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'inactive',
            daily_limit INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (booster_id) REFERENCES boosters(id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_cards (
            user_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            obtained_at TEXT NOT NULL,
            draw_id TEXT,
            draw_name TEXT,
            booster_id TEXT,
            booster_name TEXT,
            PRIMARY KEY (user_id, card_id),
            FOREIGN KEY (card_id) REFERENCES cards(id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS booster_openings (
            opening_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            draw_id TEXT NOT NULL,
            booster_id TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            cost_points INTEGER NOT NULL,
            cards_rolled TEXT NOT NULL,
            total_refund INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_daily_opens (
            user_id TEXT NOT NULL,
            day TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cards_meta (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            daily_open_limit INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await conn.execute(
        "INSERT OR IGNORE INTO cards_meta (id, daily_open_limit) VALUES (1, 0)"
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    await conn.execute(
        "INSERT OR IGNORE INTO card_series (id, name, sort_order) VALUES (?, ?, 0)",
        (_SERIES_ID, _SERIES_NAME),
    )
    for idx, (card_id, name, rarity) in enumerate(_CARDS):
        await conn.execute(
            """
            INSERT OR IGNORE INTO cards (id, series_id, name, rarity, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (card_id, _SERIES_ID, name, rarity, idx),
        )
    await conn.execute(
        """
        INSERT OR IGNORE INTO boosters (id, name, promo_image_url, created_at)
        VALUES (?, ?, NULL, ?)
        """,
        (_BOOSTER_ID, _BOOSTER_NAME, now),
    )
    for card_id, _, _ in _CARDS:
        await conn.execute(
            """
            INSERT OR IGNORE INTO booster_pool (booster_id, card_id)
            VALUES (?, ?)
            """,
            (_BOOSTER_ID, card_id),
        )
    await conn.execute(
        """
        INSERT OR IGNORE INTO draws (
            id, booster_id, name, cost_points, cards_per_open,
            rarity_weights, status, daily_limit, created_at
        ) VALUES (?, ?, ?, 1000, 6, ?, 'active', 0, ?)
        """,
        (
            _DRAW_ID,
            _BOOSTER_ID,
            _DRAW_NAME,
            json.dumps(_DEFAULT_WEIGHTS, ensure_ascii=False),
            now,
        ),
    )


async def seed_if_empty(conn: aiosqlite.Connection) -> None:
    """Заполнить каталог на свежей БД (когда миграции пропущены из-за SCHEMA_VERSION)."""
    cur = await conn.execute("SELECT COUNT(*) FROM card_series")
    row = await cur.fetchone()
    if row and int(row[0]) > 0:
        return
    await upgrade(conn)
