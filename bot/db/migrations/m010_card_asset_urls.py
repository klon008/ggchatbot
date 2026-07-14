"""Migration 010: image_url → локальные /assets/cards/{slug}.webp для админки."""

from __future__ import annotations

import aiosqlite

from .m009_elsa_mythic import portrait_path, upsert_catalog_and_images

VERSION = 10
DESCRIPTION = "Карты: image_url указывает на obs/assets/cards (для Admin)"


async def upgrade(conn: aiosqlite.Connection) -> None:
    # Перезаписать пути и убедиться, что каталог актуален
    await upsert_catalog_and_images(conn)
    # На всякий случай: все slug → /assets/cards/{id}.webp
    cur = await conn.execute("SELECT id FROM cards")
    rows = await cur.fetchall()
    for (card_id,) in rows:
        await conn.execute(
            "UPDATE cards SET image_url = ? WHERE id = ?",
            (portrait_path(card_id), card_id),
        )
