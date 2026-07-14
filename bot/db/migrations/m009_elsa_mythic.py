"""Migration 009: Эльза (Mythic) + image_url у карт."""

from __future__ import annotations

import json

import aiosqlite

VERSION = 9
DESCRIPTION = "Карты: image_url; Эльза (mythic) в каталоге и стартовом бустере"

_SERIES_ID = "fantast"
_BOOSTER_ID = "start"

# slug → (name, rarity, sort_order) — полный каталог MVP (28 карт)
_CATALOG: list[tuple[str, str, str, int]] = [
    ("cinderella", "Золушка", "common", 0),
    ("belle", "Белль", "uncommon", 1),
    ("ariel", "Ариэль", "rare", 2),
    ("snow-white", "Белоснежка", "common", 3),
    ("rapunzel", "Рапунцель", "epic", 4),
    ("jasmine", "Жасмин", "uncommon", 5),
    ("moana", "Моана", "rare", 6),
    ("pocahontas", "Покахонтас", "common", 7),
    ("aurora", "Аврора", "legendary", 8),
    ("tiana", "Тиана", "uncommon", 9),
    ("merida", "Мерида", "rare", 10),
    ("asha", "Аша", "common", 11),
    ("raya", "Рая", "epic", 12),
    ("mulan", "Мулан", "uncommon", 13),
    ("anna", "Анна", "rare", 14),
    ("nala", "Нала", "common", 15),
    ("queen-elsa", "Королева Эльза", "secretRare", 16),
    ("megara", "Мегара", "secretRare", 17),
    ("esmeralda", "Эсмеральда", "rare", 18),
    ("jane", "Джейн", "common", 19),
    ("mirabel", "Мирабель", "epic", 20),
    ("tinker-bell", "Динь-Динь", "uncommon", 21),
    ("kida", "Кида", "rare", 22),
    ("giselle", "Жизель", "uncommon", 23),
    ("flounder", "Флаундер", "common", 24),
    ("olaf", "Олаф", "common", 25),
    ("pascal", "Паскаль", "common", 26),
    ("elsa", "Эльза", "mythic", 27),
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


def portrait_path(slug: str) -> str:
    """Локальный URL арта для OBS-админки (раздаётся ботом с :8765)."""
    return f"/assets/cards/{slug}.webp"


async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    cur = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return any(r[1] == column for r in rows)


async def ensure_image_url_column(conn: aiosqlite.Connection) -> None:
    if not await _column_exists(conn, "cards", "image_url"):
        await conn.execute("ALTER TABLE cards ADD COLUMN image_url TEXT")


async def upsert_catalog_and_images(conn: aiosqlite.Connection) -> None:
    await ensure_image_url_column(conn)
    for card_id, name, rarity, sort_order in _CATALOG:
        await conn.execute(
            """
            INSERT INTO cards (id, series_id, name, rarity, sort_order, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                rarity = excluded.rarity,
                sort_order = excluded.sort_order,
                image_url = excluded.image_url
            """,
            (card_id, _SERIES_ID, name, rarity, sort_order, portrait_path(card_id)),
        )
        await conn.execute(
            """
            INSERT OR IGNORE INTO booster_pool (booster_id, card_id)
            VALUES (?, ?)
            """,
            (_BOOSTER_ID, card_id),
        )


async def merge_mythic_into_draw_weights(conn: aiosqlite.Connection) -> None:
    cur = await conn.execute("SELECT id, rarity_weights FROM draws")
    rows = await cur.fetchall()
    for draw_id, raw in rows:
        try:
            weights = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            weights = {}
        if "mythic" not in weights:
            weights["mythic"] = _DEFAULT_WEIGHTS["mythic"]
            await conn.execute(
                "UPDATE draws SET rarity_weights = ? WHERE id = ?",
                (json.dumps(weights, ensure_ascii=False), draw_id),
            )


async def upgrade(conn: aiosqlite.Connection) -> None:
    await upsert_catalog_and_images(conn)
    await merge_mythic_into_draw_weights(conn)


async def seed_if_empty(conn: aiosqlite.Connection) -> None:
    """Полный сид каталога на свежей БД (tables уже из schema.py)."""
    cur = await conn.execute("SELECT COUNT(*) FROM cards")
    row = await cur.fetchone()
    if row and int(row[0]) > 0:
        # Подтянуть недостающее (Эльза / image_url) даже если seed уже частично был
        await upgrade(conn)
        return
    # Пусто — делегируем создание базовых бустеров в m008, затем дописываем каталог
    from . import m008_cards

    await m008_cards.upgrade(conn)
    await upgrade(conn)
