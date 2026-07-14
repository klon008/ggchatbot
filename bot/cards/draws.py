"""Логика открытия бустера: броски, дубли, возврат баллов."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

from bot.db import Database
from bot.db import cards as cards_db

from .constants import RARITY_LABELS

if TYPE_CHECKING:
    from bot.economy.points import PointsStore


@dataclass
class RollResult:
    card_id: str
    card_name: str
    rarity: str
    is_duplicate: bool
    refund: int
    image_url: str = ""
    card_back_id: str = "card-back"


@dataclass
class OpenResult:
    draw_name: str
    booster_name: str
    rolls: list[RollResult]
    total_refund: int
    new_count: int
    album_count: int
    series_progress: list[dict[str, Any]]
    collection: dict[str, int]
    cost_points: int = 0
    cards_per_open: int = 0


def duplicate_refund(cost_points: int, cards_per_open: int) -> int:
    per_card = cost_points / cards_per_open
    return math.floor(per_card * 0.25)


def _pick_rarity(weights: dict[str, float]) -> str:
    items = [(r, float(w)) for r, w in weights.items() if float(w) > 0]
    if not items:
        return "common"
    total = sum(w for _, w in items)
    roll = random.uniform(0, total)
    acc = 0.0
    for rarity, weight in items:
        acc += weight
        if roll <= acc:
            return rarity
    return items[-1][0]


def _portrait_url(card: cards_db.CardRow) -> str:
    return card.image_url or f"/assets/cards/{card.id}.webp"


def _make_roll(
    card: cards_db.CardRow,
    *,
    is_duplicate: bool,
    refund: int,
) -> RollResult:
    return RollResult(
        card_id=card.id,
        card_name=card.name,
        rarity=card.rarity,
        is_duplicate=is_duplicate,
        refund=refund,
        image_url=_portrait_url(card),
        card_back_id=card.card_back_id or "card-back",
    )


async def open_booster(
    db: Database,
    points: "PointsStore",
    *,
    user_id: str,
    user_name: str,
) -> tuple[Optional[OpenResult], Optional[str]]:
    """Открыть активный тираж. Возвращает (result, error_message)."""
    draw = await cards_db.get_active_draw(db)
    if draw is None:
        return None, "Сейчас нет активного тиража."
    if draw.status == cards_db.DRAW_PAUSED:
        return None, "Тираж приостановлен."

    if draw.daily_limit > 0:
        daily_cap = draw.daily_limit
    else:
        daily_cap = await cards_db.get_global_daily_limit(db)
    if daily_cap > 0:
        opens_today = await cards_db.get_daily_opens(db, user_id)
        if opens_today >= daily_cap:
            return None, f"Лимит открытий на сегодня: {daily_cap}."

    balance = await points.get_balance(user_id)
    if balance < draw.cost_points:
        return None, (
            f"Недостаточно баллов. Нужно {draw.cost_points}, у тебя {balance}."
        )

    refund_per_dup = duplicate_refund(draw.cost_points, draw.cards_per_open)
    rolls: list[RollResult] = []
    total_refund = 0
    cards_rolled: list[dict[str, Any]] = []

    await points.add(user_id, -draw.cost_points)

    for _ in range(draw.cards_per_open):
        rarity = _pick_rarity(draw.rarity_weights)
        pool = await cards_db.list_pool_cards_by_rarity(db, draw.booster_id, rarity)
        if not pool:
            pool = await cards_db.list_pool_cards_by_rarity(db, draw.booster_id, "common")
        if not pool:
            await points.add(user_id, draw.cost_points)
            return None, "Пул бустера пуст — обратись к стримеру."

        card = random.choice(pool)
        owned = await cards_db.user_owns_card(db, user_id, card.id)
        if owned:
            refund = refund_per_dup
            total_refund += refund
            await points.add(user_id, refund)
            roll = _make_roll(card, is_duplicate=True, refund=refund)
            cards_rolled.append(
                {
                    "card_id": card.id,
                    "is_duplicate": True,
                    "refund": refund,
                }
            )
        else:
            await cards_db.add_user_card(
                db,
                user_id=user_id,
                card_id=card.id,
                draw_id=draw.id,
                draw_name=draw.name,
                booster_id=draw.booster_id,
                booster_name=draw.booster_name,
            )
            roll = _make_roll(card, is_duplicate=False, refund=0)
            cards_rolled.append({"card_id": card.id, "is_duplicate": False, "refund": 0})
        rolls.append(roll)

    await cards_db.increment_daily_opens(db, user_id)
    await cards_db.log_opening(
        db,
        user_id=user_id,
        draw_id=draw.id,
        booster_id=draw.booster_id,
        cost_points=draw.cost_points,
        cards_rolled=cards_rolled,
        total_refund=total_refund,
    )
    await points.flush_pending()
    await points.touch_name_if_new(user_id, user_name)

    new_count = sum(1 for r in rolls if not r.is_duplicate)
    album_count = await cards_db.count_user_cards(db, user_id)
    series_progress = await cards_db.count_series_progress(db, user_id)
    collection = await cards_db.count_collection(db, user_id)

    return (
        OpenResult(
            draw_name=draw.name,
            booster_name=draw.booster_name,
            rolls=rolls,
            total_refund=total_refund,
            new_count=new_count,
            album_count=album_count,
            series_progress=series_progress,
            collection=collection,
            cost_points=draw.cost_points,
            cards_per_open=draw.cards_per_open,
        ),
        None,
    )


def _dup_phrase(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} дубль"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return f"{n} дубля"
    return f"{n} дублей"


def format_open_start(user_name: str, result: OpenResult) -> str:
    """Шаг 1: анонс перед OBS-анимацией."""
    return (
        f"{user_name}, открывает {result.booster_name} ({result.draw_name}): "
        f"{result.cards_per_open} карт, стоимость - {result.cost_points} принцесс."
    )


def format_open_summary(user_name: str, result: OpenResult) -> str:
    """Шаг 2: итог с группировкой дублей."""
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for roll in result.rolls:
        g = groups.get(roll.card_id)
        if g is None:
            g = {
                "name": roll.card_name,
                "rarity": roll.rarity,
                "new": 0,
                "dups": 0,
                "refund": 0,
            }
            groups[roll.card_id] = g
            order.append(roll.card_id)
        if roll.is_duplicate:
            g["dups"] += 1
            g["refund"] += roll.refund
        else:
            g["new"] += 1

    lines = [
        f"{user_name}, открытие завершено!",
        "Внутри было:",
    ]
    for card_id in order:
        g = groups[card_id]
        label = RARITY_LABELS.get(g["rarity"], g["rarity"])
        head = f"• {g['name']} ({label}) - "
        parts: list[str] = []
        if g["new"]:
            parts.append("новая" if g["new"] == 1 else f"{g['new']} новых")
        if g["dups"]:
            part = _dup_phrase(g["dups"])
            if g["refund"]:
                part += f" (возврат: {g['refund']} принцессы)"
            parts.append(part)
        lines.append(head + " + ".join(parts))
    lines.append("Загляни в альбом: !альбом")
    return "\n".join(lines)


def opening_to_ws_payload(
    opening_id: str,
    user_name: str,
    result: OpenResult,
    *,
    anim_speed: float = 1.0,
) -> dict[str, Any]:
    """Payload для OBS Browser Source (action: booster_open)."""
    return {
        "action": "booster_open",
        "openingId": opening_id,
        "userName": user_name,
        "boosterName": result.booster_name,
        "drawName": result.draw_name,
        "costPoints": result.cost_points,
        "animSpeed": float(anim_speed),
        "cards": [
            {
                "id": r.card_id,
                "name": r.card_name,
                "rarity": r.rarity,
                "isDuplicate": r.is_duplicate,
                "refund": r.refund,
                "imageUrl": r.image_url or f"/assets/cards/{r.card_id}.webp",
                "cardBackUrl": f"/assets/cards/{r.card_back_id or 'card-back'}.svg",
            }
            for r in result.rolls
        ],
    }
