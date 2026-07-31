"""Migration 027: per-draw booster stats + backfill from booster_openings."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import aiosqlite

VERSION = 27
DESCRIPTION = "Таблицы draw_user_stats, draw_card_stats + backfill из booster_openings"


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draw_user_stats (
            draw_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            opens INTEGER NOT NULL DEFAULT 0,
            spent_points INTEGER NOT NULL DEFAULT 0,
            refund_points INTEGER NOT NULL DEFAULT 0,
            dup_count INTEGER NOT NULL DEFAULT 0,
            new_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (draw_id, user_id)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS draw_card_stats (
            draw_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            appear_count INTEGER NOT NULL DEFAULT 0,
            dup_count INTEGER NOT NULL DEFAULT 0,
            new_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (draw_id, card_id)
        )
        """
    )

    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='booster_openings'"
    ) as cur:
        if await cur.fetchone() is None:
            return

    user_acc: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {
            "opens": 0,
            "spent_points": 0,
            "refund_points": 0,
            "dup_count": 0,
            "new_count": 0,
        }
    )
    card_acc: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"appear_count": 0, "dup_count": 0, "new_count": 0}
    )

    async with conn.execute(
        "SELECT draw_id, user_id, cost_points, total_refund, cards_rolled "
        "FROM booster_openings"
    ) as cur:
        rows = await cur.fetchall()

    for row in rows:
        draw_id = str(row[0])
        user_id = str(row[1])
        cost_points = int(row[2] or 0)
        total_refund = int(row[3] or 0)
        raw_rolled = row[4]
        cards_rolled = _parse_cards_rolled(raw_rolled)

        u = user_acc[(draw_id, user_id)]
        u["opens"] += 1
        u["spent_points"] += cost_points
        u["refund_points"] += total_refund

        for item in cards_rolled:
            card_id = str(item.get("card_id") or "").strip()
            if not card_id:
                continue
            is_dup = bool(item.get("is_duplicate"))
            if is_dup:
                u["dup_count"] += 1
            else:
                u["new_count"] += 1
            c = card_acc[(draw_id, card_id)]
            c["appear_count"] += 1
            if is_dup:
                c["dup_count"] += 1
            else:
                c["new_count"] += 1

    for (draw_id, user_id), stats in user_acc.items():
        await conn.execute(
            """
            INSERT INTO draw_user_stats (
                draw_id, user_id, opens, spent_points, refund_points,
                dup_count, new_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draw_id,
                user_id,
                stats["opens"],
                stats["spent_points"],
                stats["refund_points"],
                stats["dup_count"],
                stats["new_count"],
            ),
        )

    for (draw_id, card_id), stats in card_acc.items():
        await conn.execute(
            """
            INSERT INTO draw_card_stats (
                draw_id, card_id, appear_count, dup_count, new_count
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                draw_id,
                card_id,
                stats["appear_count"],
                stats["dup_count"],
                stats["new_count"],
            ),
        )


def _parse_cards_rolled(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [x for x in parsed if isinstance(x, dict)]
