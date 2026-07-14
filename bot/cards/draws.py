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
            roll = RollResult(
                card_id=card.id,
                card_name=card.name,
                rarity=card.rarity,
                is_duplicate=True,
                refund=refund,
            )
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
            roll = RollResult(
                card_id=card.id,
                card_name=card.name,
                rarity=card.rarity,
                is_duplicate=False,
                refund=0,
            )
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
        ),
        None,
    )


def format_open_chat(result: OpenResult) -> str:
    lines = [
        f"Тираж «{result.draw_name}» · Бустер «{result.booster_name}»",
    ]
    for roll in result.rolls:
        label = RARITY_LABELS.get(roll.rarity, roll.rarity)
        if roll.is_duplicate:
            lines.append(
                f"  ✦ {roll.card_name} ({label}) — дубль, возврат {roll.refund} балла"
            )
        else:
            lines.append(f"  ✦ {roll.card_name} ({label}) — новая!")
    lines.append(f"Итого: {result.new_count} новых. Альбом: {result.album_count} карт.")
    if result.series_progress:
        s = result.series_progress[0]
        lines.append(f"Серия «{s['name']}»: {s['owned']} из {s['total']}.")
    lines.append("!альбом — ссылка на альбом.")
    return "\n".join(lines)
