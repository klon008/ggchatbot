"""Migration 011: рубашка серии + переименовать бустер «Старт»."""

from __future__ import annotations

import aiosqlite

VERSION = 11
DESCRIPTION = "card_series.card_back_id; бустер start → «Стартовый набор»"

_DEFAULT_BACK_ID = "card-back"
_SERIES_ID = "fantast"
_BOOSTER_ID = "start"
_BOOSTER_NAME = "Стартовый набор"


async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    cur = await conn.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return any(r[1] == column for r in rows)


def card_back_asset_url(back_id: str) -> str:
    """Локальный URL для OBS admin: /assets/cards/card-back.svg"""
    return f"/assets/cards/{back_id}.svg"


async def upgrade(conn: aiosqlite.Connection) -> None:
    if not await _column_exists(conn, "card_series", "card_back_id"):
        await conn.execute(
            "ALTER TABLE card_series ADD COLUMN card_back_id TEXT NOT NULL DEFAULT 'card-back'"
        )

    # MVP-серия → дефолтная рубашка (src/imports/card-back.svg)
    await conn.execute(
        """
        UPDATE card_series
        SET card_back_id = ?
        WHERE id = ? OR card_back_id IS NULL OR TRIM(card_back_id) = ''
        """,
        (_DEFAULT_BACK_ID, _SERIES_ID),
    )
    await conn.execute(
        "UPDATE card_series SET card_back_id = ? WHERE card_back_id IS NULL OR card_back_id = ''",
        (_DEFAULT_BACK_ID,),
    )

    await conn.execute(
        "UPDATE boosters SET name = ? WHERE id = ?",
        (_BOOSTER_NAME, _BOOSTER_ID),
    )
    # Снимки в user_cards для отображения (старые «Старт» → новое имя)
    await conn.execute(
        "UPDATE user_cards SET booster_name = ? WHERE booster_id = ?",
        (_BOOSTER_NAME, _BOOSTER_ID),
    )
