from __future__ import annotations

import random
import secrets
import time
from typing import TYPE_CHECKING, Optional

from bot.fishing import has_steal_safe
from bot.goodgame import ChatMessage

from ..economy import (
    apply_attempt_growth,
    now_msk,
    prison_chance_for_amount,
    roll_steal_amount,
)
from ..settings import (
    PRISON_DURATION_SEC,
    STEAL_AMOUNT_FLOOR,
    STEAL_BANK_AMOUNT_MULT,
    STEAL_BANK_JACKPOT_CHANCE,
    STEAL_COOLDOWN_SEC,
    STEAL_MIN_VIEWERS,
    STEAL_ROLL_MAX,
    VICTIM_MIN_BALANCE,
)

if TYPE_CHECKING:
    from bot.princess.handler import PrincessHandler

POOR_VICTIM_MESSAGES = [
    "У {name} меньше 3к — мимо.",
    "{name} слишком беден. Мимо.",
    "У {name} пусто. Некого грабить.",
]

SAFE_VICTIM_MESSAGES = [
    "У {name} сейф — кража сорвалась.",
    "Сейф {name} не поддался.",
]


async def cmd_steal(handler: "PrincessHandler", msg: ChatMessage) -> None:
    if not await handler.steal.is_allowed():
        await handler._say(msg.user_name, "Кража сейчас недоступна.")
        return

    await handler._refresh_viewers()
    if len(handler._viewers) < STEAL_MIN_VIEWERS:
        await handler._say(
            msg.user_name,
            f"Мало зрителей. Нужно минимум {STEAL_MIN_VIEWERS}.",
        )
        return

    uid = msg.user_id
    today_key = now_msk().strftime("%Y-%m-%d")
    async with handler.steal.mutate_info(uid) as info:
        now = time.time()
        if now - info["last_time"] < STEAL_COOLDOWN_SEC:
            await handler._say(msg.user_name, "Раз в 10 минут.")
            return

        info["last_time"] = now
        info["attempts"] += 1
        info["last_steal_day_key"] = today_key
        apply_attempt_growth(info)
        chance = int(info["chance"])

    roll = random.randint(1, STEAL_ROLL_MAX)
    if roll > chance:
        await handler._say(msg.user_name, "Провал.")
        return

    tiers = await handler.steal.get_loot_tiers()
    bank_jackpot = False
    stolen = 0
    victim_id: Optional[str] = None
    victim_name = ""

    if random.random() < STEAL_BANK_JACKPOT_CHANCE:
        base = roll_steal_amount(tiers)
        desired = base * STEAL_BANK_AMOUNT_MULT
        min_required = STEAL_AMOUNT_FLOOR * STEAL_BANK_AMOUNT_MULT
        taken = await handler.steal.execute_bank_steal(
            handler.points, uid, desired, min_required=min_required
        )
        if taken is not None:
            stolen = taken
            bank_jackpot = True

    if not bank_jackpot:
        candidates = [v for v in handler._viewers if v != uid]
        if not candidates:
            await handler._say(msg.user_name, "Никого нет в чате.")
            return

        victim_id = secrets.choice(candidates)
        victim_name = handler._viewers[victim_id]["user_name"]
        victim_points = await handler.points.get_balance(victim_id)

        if victim_points < VICTIM_MIN_BALANCE:
            msg_text = random.choice(POOR_VICTIM_MESSAGES).format(name=victim_name)
            await handler._say(msg.user_name, msg_text)
            return

        if await has_steal_safe(handler._db, victim_id):
            msg_text = random.choice(SAFE_VICTIM_MESSAGES).format(name=victim_name)
            await handler._say(msg.user_name, msg_text)
            return

        max_possible = max(0, victim_points - VICTIM_MIN_BALANCE)
        amount = min(roll_steal_amount(tiers), max_possible)
        if amount < STEAL_AMOUNT_FLOOR:
            await handler._say(msg.user_name, "У жертвы почти пусто. Мимо.")
            return

        stolen = amount
        await handler.steal.execute_steal(handler.points, uid, victim_id, stolen)

    chance_to_prison = prison_chance_for_amount(stolen)
    caught = bool(
        chance_to_prison and random.randint(1, STEAL_ROLL_MAX) <= chance_to_prison
    )

    if caught:
        if bank_jackpot:
            await handler.steal.revert_bank_steal(handler.points, uid, stolen)
        elif victim_id is not None:
            await handler.steal.revert_steal(handler.points, uid, victim_id, stolen)
        await handler.prison.imprison(uid)
        await handler.steal.increment_jail_count(uid)
        prison_minutes = PRISON_DURATION_SEC // 60
        await handler._say(
            msg.user_name,
            f"Поймали! Вернули {stolen}. Тюрьма {prison_minutes} мин.",
        )
        return

    if bank_jackpot:
        await handler._say(msg.user_name, f"Джекпот! {stolen} из казны.")
    else:
        await handler._say(msg.user_name, f"Унёс {stolen} у {victim_name}.")
