"""SQLite-доступ к коллекционным картам."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from bot.db import Database

RARITIES = (
    "common",
    "uncommon",
    "rare",
    "epic",
    "legendary",
    "mythic",
    "secretRare",
)
DRAW_ACTIVE = "active"
DRAW_PAUSED = "paused"
DRAW_QUEUED = "queued"
DRAW_CLOSED = "closed"
# Устаревший статус (миграция m013 → closed)
DRAW_INACTIVE = "inactive"


@dataclass
class CardRow:
    id: str
    series_id: str
    series_name: str
    name: str
    rarity: str
    sort_order: int
    image_url: str = ""
    card_back_id: str = "card-back"


@dataclass
class DrawRow:
    id: str
    booster_id: str
    booster_name: str
    name: str
    cost_points: int
    cards_per_open: int
    rarity_weights: dict[str, float]
    status: str
    daily_limit: int


@dataclass
class OwnedCardRow:
    id: str
    name: str
    rarity: str
    obtained_at: str
    draw_name: str
    booster_name: str
    image_url: str = ""
    series_id: str = ""
    card_back_id: str = "card-back"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def get_active_draw(db: Database) -> Optional[DrawRow]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT d.id, d.booster_id, b.name AS booster_name, d.name,
                   d.cost_points, d.cards_per_open, d.rarity_weights,
                   d.status, d.daily_limit
            FROM draws d
            JOIN boosters b ON b.id = d.booster_id
            WHERE d.status = ?
            LIMIT 1
            """,
            (DRAW_ACTIVE,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return DrawRow(
        id=row[0],
        booster_id=row[1],
        booster_name=row[2],
        name=row[3],
        cost_points=int(row[4]),
        cards_per_open=int(row[5]),
        rarity_weights=json.loads(row[6]),
        status=row[7],
        daily_limit=int(row[8]),
    )


async def list_pool_cards_by_rarity(
    db: Database, booster_id: str, rarity: str
) -> list[CardRow]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT c.id, c.series_id, s.name, c.name, c.rarity, c.sort_order,
                   COALESCE(c.image_url, ''),
                   COALESCE(s.card_back_id, 'card-back')
            FROM booster_pool bp
            JOIN cards c ON c.id = bp.card_id
            JOIN card_series s ON s.id = c.series_id
            WHERE bp.booster_id = ? AND c.rarity = ?
            ORDER BY c.sort_order
            """,
            (booster_id, rarity),
        )
        rows = await cur.fetchall()
    return [
        CardRow(
            id=r[0],
            series_id=r[1],
            series_name=r[2],
            name=r[3],
            rarity=r[4],
            sort_order=int(r[5]),
            image_url=r[6] or "",
            card_back_id=r[7] or "card-back",
        )
        for r in rows
    ]


async def user_owns_card(db: Database, user_id: str, card_id: str) -> bool:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM user_cards WHERE user_id = ? AND card_id = ? LIMIT 1",
            (user_id, card_id),
        )
        return await cur.fetchone() is not None


async def add_user_card(
    db: Database,
    *,
    user_id: str,
    card_id: str,
    draw_id: str,
    draw_name: str,
    booster_id: str,
    booster_name: str,
) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO user_cards (
                user_id, card_id, obtained_at, draw_id, draw_name, booster_id, booster_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, card_id, _utc_now(), draw_id, draw_name, booster_id, booster_name),
        )


async def count_user_cards(db: Database, user_id: str) -> int:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM user_cards WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


def _series_progress_rows(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": r[0],
            "name": r[1],
            "total": int(r[2]),
            "owned": int(r[3]),
            "card_back_id": r[4] or "card-back",
        }
        for r in rows
    ]


async def count_series_progress(db: Database, user_id: str) -> list[dict[str, Any]]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT s.id, s.name,
                   (SELECT COUNT(*) FROM cards c WHERE c.series_id = s.id) AS total,
                   (SELECT COUNT(*) FROM user_cards uc
                    JOIN cards c2 ON c2.id = uc.card_id
                    WHERE uc.user_id = ? AND c2.series_id = s.id) AS owned,
                   COALESCE(s.card_back_id, 'card-back') AS card_back_id
            FROM card_series s
            ORDER BY s.sort_order, s.name
            """,
            (user_id,),
        )
        rows = await cur.fetchall()
    return _series_progress_rows(rows)


async def count_series_progress_for_booster(
    db: Database, user_id: str, booster_id: str
) -> list[dict[str, Any]]:
    """Прогресс по сериям, которые есть в пуле бустера (обычно одна)."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT s.id, s.name,
                   (SELECT COUNT(*) FROM cards c WHERE c.series_id = s.id) AS total,
                   (SELECT COUNT(*) FROM user_cards uc
                    JOIN cards c2 ON c2.id = uc.card_id
                    WHERE uc.user_id = ? AND c2.series_id = s.id) AS owned,
                   COALESCE(s.card_back_id, 'card-back') AS card_back_id
            FROM card_series s
            WHERE s.id IN (
                SELECT DISTINCT c.series_id
                FROM booster_pool bp
                JOIN cards c ON c.id = bp.card_id
                WHERE bp.booster_id = ?
            )
            ORDER BY s.sort_order, s.name
            """,
            (user_id, booster_id),
        )
        rows = await cur.fetchall()
    return _series_progress_rows(rows)


async def count_collection(db: Database, user_id: str) -> dict[str, int]:
    async with db.transaction() as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM cards")
        total_row = await cur.fetchone()
        cur = await conn.execute(
            "SELECT COUNT(*) FROM user_cards WHERE user_id = ?",
            (user_id,),
        )
        owned_row = await cur.fetchone()
    return {"owned": int(owned_row[0]), "total": int(total_row[0])}


async def list_owned_cards(db: Database, user_id: str) -> list[OwnedCardRow]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT c.id, c.name, c.rarity, uc.obtained_at,
                   COALESCE(uc.draw_name, ''), COALESCE(uc.booster_name, ''),
                   COALESCE(c.image_url, ''),
                   c.series_id,
                   COALESCE(s.card_back_id, 'card-back')
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            JOIN card_series s ON s.id = c.series_id
            WHERE uc.user_id = ?
            ORDER BY c.sort_order
            """,
            (user_id,),
        )
        rows = await cur.fetchall()
    return [
        OwnedCardRow(
            id=r[0],
            name=r[1],
            rarity=r[2],
            obtained_at=r[3][:10] if r[3] else "",
            draw_name=r[4] or "",
            booster_name=r[5] or "",
            image_url=r[6] or "",
            series_id=r[7] or "",
            card_back_id=r[8] or "card-back",
        )
        for r in rows
    ]


async def get_user_id_by_nick(db: Database, nick_lower: str) -> Optional[str]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT user_id FROM user_names
            WHERE LOWER(user_name) = ?
            LIMIT 1
            """,
            (nick_lower,),
        )
        row = await cur.fetchone()
    return str(row[0]) if row else None


async def get_user_name(db: Database, user_id: str) -> str:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT user_name FROM user_names WHERE user_id = ? LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
    if not row or not row[0]:
        return ""
    return str(row[0])


async def increment_daily_opens(db: Database, user_id: str) -> int:
    day = _today()
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO user_daily_opens (user_id, day, count) VALUES (?, ?, 1)
            ON CONFLICT(user_id, day) DO UPDATE SET count = count + 1
            """,
            (user_id, day),
        )
        cur = await conn.execute(
            "SELECT count FROM user_daily_opens WHERE user_id = ? AND day = ?",
            (user_id, day),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 1


async def get_daily_opens(db: Database, user_id: str) -> int:
    day = _today()
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT count FROM user_daily_opens WHERE user_id = ? AND day = ?",
            (user_id, day),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def log_opening(
    db: Database,
    *,
    user_id: str,
    draw_id: str,
    booster_id: str,
    cost_points: int,
    cards_rolled: list[dict[str, Any]],
    total_refund: int,
) -> str:
    opening_id = uuid.uuid4().hex
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO booster_openings (
                opening_id, user_id, draw_id, booster_id, opened_at,
                cost_points, cards_rolled, total_refund
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opening_id,
                user_id,
                draw_id,
                booster_id,
                _utc_now(),
                cost_points,
                json.dumps(cards_rolled, ensure_ascii=False),
                total_refund,
            ),
        )
    return opening_id


async def get_booster_promo_url(db: Database, booster_id: str) -> Optional[str]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT promo_image_url FROM boosters WHERE id = ?",
            (booster_id,),
        )
        row = await cur.fetchone()
    if row is None or not row[0]:
        return None
    return str(row[0])


async def get_global_daily_limit(db: Database) -> int:
    meta = await get_cards_meta(db)
    return int(meta["daily_open_limit"])


async def set_global_daily_limit(db: Database, limit: int) -> None:
    await set_cards_meta(db, daily_open_limit=max(0, limit))


ANIM_SPEED_MIN = 0.5
ANIM_SPEED_MAX = 3.0
ANIM_SPEED_DEFAULT = 1.0


def clamp_anim_speed(value: float) -> float:
    return max(ANIM_SPEED_MIN, min(ANIM_SPEED_MAX, float(value)))


async def get_cards_meta(db: Database) -> dict[str, Any]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT daily_open_limit,
                   COALESCE(enabled, 1),
                   COALESCE(anim_speed, 1.0)
            FROM cards_meta WHERE id = 1
            """
        )
        row = await cur.fetchone()
    if row is None:
        return {
            "daily_open_limit": 0,
            "enabled": True,
            "anim_speed": ANIM_SPEED_DEFAULT,
        }
    return {
        "daily_open_limit": int(row[0]),
        "enabled": bool(row[1]),
        "anim_speed": clamp_anim_speed(row[2] if row[2] is not None else ANIM_SPEED_DEFAULT),
    }


async def set_cards_meta(
    db: Database,
    *,
    daily_open_limit: Optional[int] = None,
    enabled: Optional[bool] = None,
    anim_speed: Optional[float] = None,
) -> dict[str, Any]:
    current = await get_cards_meta(db)
    new_limit = (
        max(0, int(daily_open_limit))
        if daily_open_limit is not None
        else int(current["daily_open_limit"])
    )
    new_enabled = bool(enabled) if enabled is not None else bool(current["enabled"])
    new_speed = (
        clamp_anim_speed(anim_speed)
        if anim_speed is not None
        else float(current["anim_speed"])
    )
    async with db.transaction() as conn:
        await conn.execute(
            """
            UPDATE cards_meta
            SET daily_open_limit = ?, enabled = ?, anim_speed = ?
            WHERE id = 1
            """,
            (new_limit, 1 if new_enabled else 0, new_speed),
        )
    return {
        "daily_open_limit": new_limit,
        "enabled": new_enabled,
        "anim_speed": new_speed,
    }


async def list_series(db: Database) -> list[dict[str, Any]]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT s.id, s.name, s.sort_order,
                   COALESCE(s.card_back_id, 'card-back') AS card_back_id,
                   (SELECT COUNT(*) FROM cards c WHERE c.series_id = s.id) AS cards_count
            FROM card_series s
            ORDER BY s.sort_order, s.name
            """
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "sort_order": int(r[2] or 0),
            "card_back_id": r[3] or "card-back",
            "cards_count": int(r[4]),
        }
        for r in rows
    ]


async def series_exists(db: Database, series_id: str) -> bool:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM card_series WHERE id = ? LIMIT 1",
            (series_id,),
        )
        return await cur.fetchone() is not None


async def update_series(
    db: Database,
    *,
    series_id: str,
    name: str,
    sort_order: int,
    card_back_id: str,
) -> Optional[dict[str, Any]]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            UPDATE card_series
            SET name = ?, sort_order = ?, card_back_id = ?
            WHERE id = ?
            """,
            (name, sort_order, card_back_id, series_id),
        )
        if cur.rowcount == 0:
            return None
    items = await list_series(db)
    return next((s for s in items if s["id"] == series_id), None)


async def list_catalog_cards(db: Database) -> list[dict[str, Any]]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT c.id, c.name, c.rarity, c.series_id, s.name AS series_name,
                   c.sort_order, COALESCE(c.image_url, '')
            FROM cards c
            JOIN card_series s ON s.id = c.series_id
            ORDER BY c.sort_order
            """
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "rarity": r[2],
            "series_id": r[3],
            "series_name": r[4],
            "sort_order": int(r[5]),
            "image_url": r[6] or "",
        }
        for r in rows
    ]


async def list_boosters(db: Database) -> list[dict[str, Any]]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT id, name, promo_image_url, created_at FROM boosters ORDER BY created_at"
        )
        rows = await cur.fetchall()
    items = []
    for r in rows:
        pool = await list_booster_pool_ids(db, r[0])
        items.append(
            {
                "id": r[0],
                "name": r[1],
                "promo_image_url": r[2],
                "created_at": r[3],
                "card_ids": pool,
            }
        )
    return items


async def list_booster_pool_ids(db: Database, booster_id: str) -> list[str]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT card_id FROM booster_pool WHERE booster_id = ? ORDER BY card_id",
            (booster_id,),
        )
        rows = await cur.fetchall()
    return [str(r[0]) for r in rows]


async def list_booster_pool_cards(
    db: Database, booster_id: str
) -> list[dict[str, Any]]:
    """Карты в пуле бустера: имя + редкость."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT c.id, c.name, c.rarity
            FROM booster_pool bp
            JOIN cards c ON c.id = bp.card_id
            WHERE bp.booster_id = ?
            ORDER BY c.sort_order, c.name
            """,
            (booster_id,),
        )
        rows = await cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "rarity": r[2]}
        for r in rows
    ]


async def booster_exists(db: Database, booster_id: str) -> bool:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM boosters WHERE id = ? LIMIT 1",
            (booster_id,),
        )
        return await cur.fetchone() is not None


async def create_booster(
    db: Database,
    *,
    booster_id: str,
    name: str,
    card_ids: list[str],
) -> None:
    now = _utc_now()
    async with db.transaction() as conn:
        await conn.execute(
            "INSERT INTO boosters (id, name, promo_image_url, created_at) VALUES (?, ?, NULL, ?)",
            (booster_id, name, now),
        )
        for card_id in card_ids:
            await conn.execute(
                "INSERT INTO booster_pool (booster_id, card_id) VALUES (?, ?)",
                (booster_id, card_id),
            )


async def update_booster(
    db: Database,
    *,
    booster_id: str,
    name: str,
    card_ids: list[str],
) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE boosters SET name = ? WHERE id = ?",
            (name, booster_id),
        )
        await conn.execute(
            "DELETE FROM booster_pool WHERE booster_id = ?",
            (booster_id,),
        )
        for card_id in card_ids:
            await conn.execute(
                "INSERT INTO booster_pool (booster_id, card_id) VALUES (?, ?)",
                (booster_id, card_id),
            )


async def set_booster_promo_url(
    db: Database, booster_id: str, url: Optional[str]
) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE boosters SET promo_image_url = ? WHERE id = ?",
            (url, booster_id),
        )


async def list_draws(db: Database) -> list[dict[str, Any]]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT d.id, d.booster_id, b.name, d.name, d.cost_points, d.cards_per_open,
                   d.rarity_weights, d.status, d.daily_limit, d.created_at
            FROM draws d
            JOIN boosters b ON b.id = d.booster_id
            ORDER BY d.created_at ASC
            """
        )
        rows = await cur.fetchall()
    items = [
        {
            "id": r[0],
            "booster_id": r[1],
            "booster_name": r[2],
            "name": r[3],
            "cost_points": int(r[4]),
            "cards_per_open": int(r[5]),
            "rarity_weights": json.loads(r[6]),
            "status": r[7],
            "daily_limit": int(r[8]),
            "created_at": r[9],
        }
        for r in rows
    ]
    return _enrich_draws_fifo(items)


def _enrich_draws_fifo(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Очередь FIFO: active/paused → queued (по created_at) → closed."""
    live = [d for d in items if d["status"] in (DRAW_ACTIVE, DRAW_PAUSED)]
    queued = [d for d in items if d["status"] == DRAW_QUEUED]
    closed = [
        d
        for d in items
        if d["status"] not in (DRAW_ACTIVE, DRAW_PAUSED, DRAW_QUEUED)
    ]
    closed.sort(key=lambda d: d["created_at"] or "", reverse=True)

    has_live = bool(live)
    next_id = queued[0]["id"] if queued and not has_live else None

    for i, d in enumerate(queued, start=1):
        d["queue_position"] = i
        d["can_activate"] = (not has_live) and d["id"] == next_id
    for d in live:
        d["queue_position"] = None
        d["can_activate"] = d["status"] == DRAW_PAUSED  # возобновить
    for d in closed:
        d["queue_position"] = None
        d["can_activate"] = False

    return live + queued + closed


async def get_draw(db: Database, draw_id: str) -> Optional[dict[str, Any]]:
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT d.id, d.booster_id, b.name, d.name, d.cost_points, d.cards_per_open,
                   d.rarity_weights, d.status, d.daily_limit, d.created_at
            FROM draws d
            JOIN boosters b ON b.id = d.booster_id
            WHERE d.id = ?
            """,
            (draw_id,),
        )
        r = await cur.fetchone()
    if r is None:
        return None
    return {
        "id": r[0],
        "booster_id": r[1],
        "booster_name": r[2],
        "name": r[3],
        "cost_points": int(r[4]),
        "cards_per_open": int(r[5]),
        "rarity_weights": json.loads(r[6]),
        "status": r[7],
        "daily_limit": int(r[8]),
        "created_at": r[9],
    }


async def draw_exists(db: Database, draw_id: str) -> bool:
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM draws WHERE id = ? LIMIT 1",
            (draw_id,),
        )
        return await cur.fetchone() is not None


async def create_draw(
    db: Database,
    *,
    draw_id: str,
    booster_id: str,
    name: str,
    cost_points: int,
    cards_per_open: int,
    rarity_weights: dict[str, float],
    daily_limit: int = 0,
    activate: bool = False,
) -> None:
    now = _utc_now()
    status = DRAW_ACTIVE if activate else DRAW_QUEUED
    async with db.transaction() as conn:
        if activate:
            # Текущий live уходит в closed навсегда (нельзя вернуть).
            await conn.execute(
                "UPDATE draws SET status = ? WHERE status IN (?, ?)",
                (DRAW_CLOSED, DRAW_ACTIVE, DRAW_PAUSED),
            )
        await conn.execute(
            """
            INSERT INTO draws (
                id, booster_id, name, cost_points, cards_per_open,
                rarity_weights, status, daily_limit, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draw_id,
                booster_id,
                name,
                cost_points,
                cards_per_open,
                json.dumps(rarity_weights, ensure_ascii=False),
                status,
                max(0, daily_limit),
                now,
            ),
        )


async def activate_draw(db: Database, draw_id: str) -> dict[str, Any]:
    """Активировать голову очереди (queued) или возобновить paused."""
    draw = await get_draw(db, draw_id)
    if draw is None:
        raise ValueError("not_found")
    status = draw["status"]
    if status == DRAW_CLOSED or status == DRAW_INACTIVE:
        raise ValueError("closed")
    if status == DRAW_ACTIVE:
        raise ValueError("already_active")

    if status == DRAW_PAUSED:
        async with db.transaction() as conn:
            await conn.execute(
                "UPDATE draws SET status = ? WHERE id = ?",
                (DRAW_ACTIVE, draw_id),
            )
        item = await get_draw(db, draw_id)
        assert item is not None
        return item

    if status != DRAW_QUEUED:
        raise ValueError("not_queued")

    items = await list_draws(db)
    target = next((d for d in items if d["id"] == draw_id), None)
    if target is None or not target.get("can_activate"):
        raise ValueError("not_next")

    async with db.transaction() as conn:
        # На всякий случай: не должно быть live, иначе can_activate=false.
        cur = await conn.execute(
            "SELECT id FROM draws WHERE status IN (?, ?) LIMIT 1",
            (DRAW_ACTIVE, DRAW_PAUSED),
        )
        if await cur.fetchone() is not None:
            raise ValueError("busy")
        await conn.execute(
            "UPDATE draws SET status = ? WHERE id = ?",
            (DRAW_ACTIVE, draw_id),
        )
    item = await get_draw(db, draw_id)
    assert item is not None
    return item


async def pause_draw(db: Database, draw_id: str) -> dict[str, Any]:
    draw = await get_draw(db, draw_id)
    if draw is None:
        raise ValueError("not_found")
    if draw["status"] != DRAW_ACTIVE:
        raise ValueError("not_active")
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE draws SET status = ? WHERE id = ?",
            (DRAW_PAUSED, draw_id),
        )
    item = await get_draw(db, draw_id)
    assert item is not None
    return item


async def close_draw(db: Database, draw_id: str, *, promote: bool = True) -> dict[str, Any]:
    """Завершить тираж навсегда (closed). Опционально активировать следующий в FIFO."""
    draw = await get_draw(db, draw_id)
    if draw is None:
        raise ValueError("not_found")
    if draw["status"] not in (DRAW_ACTIVE, DRAW_PAUSED):
        raise ValueError("not_live")
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE draws SET status = ? WHERE id = ?",
            (DRAW_CLOSED, draw_id),
        )
    if promote:
        await promote_next_queued(db)
    item = await get_draw(db, draw_id)
    assert item is not None
    return item


async def promote_next_queued(db: Database) -> Optional[dict[str, Any]]:
    """Активировать самый старый queued, если нет active/paused."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT id FROM draws WHERE status IN (?, ?) LIMIT 1",
            (DRAW_ACTIVE, DRAW_PAUSED),
        )
        if await cur.fetchone() is not None:
            return None
        cur = await conn.execute(
            """
            SELECT id FROM draws
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (DRAW_QUEUED,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        next_id = str(row[0])
        await conn.execute(
            "UPDATE draws SET status = ? WHERE id = ?",
            (DRAW_ACTIVE, next_id),
        )
    return await get_draw(db, next_id)


async def set_draw_status(db: Database, draw_id: str, status: str) -> None:
    """Низкоуровневая смена статуса (для совместимости). Предпочитать activate/pause/close."""
    if status == DRAW_ACTIVE:
        await activate_draw(db, draw_id)
        return
    if status == DRAW_PAUSED:
        await pause_draw(db, draw_id)
        return
    if status == DRAW_CLOSED:
        await close_draw(db, draw_id, promote=False)
        return
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE draws SET status = ? WHERE id = ?",
            (status, draw_id),
        )


async def copy_draw(
    db: Database,
    source_id: str,
    new_id: str,
    new_name: str,
    *,
    activate: bool = False,
) -> None:
    src = await get_draw(db, source_id)
    if src is None:
        raise ValueError("source draw not found")
    await create_draw(
        db,
        draw_id=new_id,
        booster_id=src["booster_id"],
        name=new_name,
        cost_points=src["cost_points"],
        cards_per_open=src["cards_per_open"],
        rarity_weights=src["rarity_weights"],
        daily_limit=src["daily_limit"],
        activate=activate,
    )
