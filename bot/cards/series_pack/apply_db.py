"""In-process DB upserts (same SQL as generated migration)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from bot.db.migrations.m009_elsa_mythic import portrait_path


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def apply_pack_to_db(
    conn: aiosqlite.Connection,
    series: dict[str, Any],
    booster: dict[str, Any],
    draw: dict[str, Any],
    cards: list[dict[str, Any]],
    *,
    schema_version: int,
) -> None:
    sid = series["id"]
    sname = series["name"]
    back = series["card_back_id"]
    sort_order = int(series.get("sort_order", 1))
    bid = booster["id"]
    bname = booster["name"]
    promo = booster.get("promo_image_url") or None
    did = draw["id"]
    dname = draw["name"]
    cost = int(draw["cost_points"])
    n_cards = int(draw["cards_per_open"])
    limit = int(draw.get("daily_limit") or 0)
    status = str(draw.get("status") or "queued")
    weights = draw.get("rarity_weights") or {}

    await conn.execute(
        """
        INSERT INTO card_series (id, name, sort_order, card_back_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            sort_order = excluded.sort_order,
            card_back_id = excluded.card_back_id
        """,
        (sid, sname, sort_order, back),
    )

    for c in cards:
        card_id = c["id"]
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
                sid,
                c["name"],
                c["rarity"],
                int(c.get("sort_order", 0)),
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
        (bid, bname, promo, now),
    )

    for c in cards:
        await conn.execute(
            """
            INSERT OR IGNORE INTO booster_pool (booster_id, card_id)
            VALUES (?, ?)
            """,
            (bid, c["id"]),
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
            did,
            bid,
            dname,
            cost,
            n_cards,
            json.dumps(
                {
                    k: float(weights.get(k, 0) or 0)
                    for k in (
                        "common",
                        "uncommon",
                        "rare",
                        "epic",
                        "legendary",
                        "mythic",
                        "secretRare",
                    )
                },
                ensure_ascii=False,
            ),
            status,
            limit,
            now,
        ),
    )

    await conn.execute(
        "UPDATE schema_version SET version = ? WHERE id = 1",
        (schema_version,),
    )
