from __future__ import annotations

import random
import secrets
import time
from typing import TYPE_CHECKING

from bot.fishing import has_steal_safe
from bot.goodgame import ChatMessage

from ..economy import (
    calculate_princess_amount,
    prison_chance_for_amount,
    update_chance,
)
from ..settings import (
    PRISON_DURATION_SEC,
    STEAL_AMOUNT_MAX,
    STEAL_AMOUNT_MIN,
    STEAL_COOLDOWN_SEC,
    STEAL_MIN_VIEWERS,
    STEAL_ROLL_MAX,
    VICTIM_MIN_BALANCE,
)

if TYPE_CHECKING:
    from bot.princess.handler import PrincessHandler

_BANK_JACKPOT_CHANCE = 0.01  # 0.1%
_BANK_AMOUNT_MULT = 2

POOR_VICTIM_MESSAGES = [
    "У {name} недостаточно крупный кошелёк. Пусть сначала накопит немного",
    "{name} слишком бедный. Нет смысла красть",
    "{name} доедает последний *** без соли. Лучше укради у кого-нибудь еще",
    "У {name} менее 18к принцесс. Не трогай его",
    "Хочешь украсть у {name}? Не надо, там слишком мало богатств",
    "Пытаешься красть у нищего {name}? Знаешь, я был о тебе лучшего мнения",
    "Я просканировал кошелек {name}. Там пока что нет 18к принцесс",
    "У жертвы должно быть не менее 18к принцесс. У {name} нет столько",
]

SAFE_VICTIM_MESSAGES = [
    "У {name} карманный сейф — принцессы под замком. Кража сорвалась!",
    "Тянешься к кошельку {name}, но карманный сейф не поддаётся. Пусто.",
    "{name} сегодня под защитой сейфа. Попробуй удачу на ком-то другом.",
]


async def cmd_steal(handler: "PrincessHandler", msg: ChatMessage) -> None:
    if not await handler.steal.is_allowed():
        await handler._say(
            msg.user_name,
            "Кража сейчас недоступна (обычно среда и пятница).",
        )
        return

    await handler._refresh_viewers()
    if len(handler._viewers) < STEAL_MIN_VIEWERS:
        await handler._say(
            msg.user_name,
            f"Вокруг слишком мало людей. Тебя могут заметить. Нужно минимум {STEAL_MIN_VIEWERS}",
        )
        return

    uid = msg.user_id
    async with handler.steal.mutate_info(uid) as info:
        now = time.time()
        if now - info["last_time"] < STEAL_COOLDOWN_SEC:
            await handler._say(msg.user_name, "Команду можно использовать раз в 10 минут.")
            return

        info["last_time"] = now
        info["attempts"] += 1
        update_chance(info)
        chance = info["chance"]

    roll = random.randint(1, STEAL_ROLL_MAX)
    if roll > chance:
        await handler._say(msg.user_name, "Провал! Тебе не удалось ничего утащить.")
        return

    stolen = calculate_princess_amount(chance)
    bank_jackpot = False

    if random.random() < _BANK_JACKPOT_CHANCE:
        lo = STEAL_AMOUNT_MIN * _BANK_AMOUNT_MULT
        hi = STEAL_AMOUNT_MAX * _BANK_AMOUNT_MULT
        desired = random.randint(lo, hi)
        taken = await handler.steal.execute_bank_steal(
            handler.points, uid, desired, min_required=lo
        )
        if taken is not None:
            stolen = taken
            bank_jackpot = True
            await handler._say(
                msg.user_name,
                f"ДЖЕКПОТ! Ты утащил {stolen} принцесс из казны мини-игр!",
            )

    if not bank_jackpot:
        candidates = [v for v in handler._viewers if v != uid]
        if not candidates:
            await handler._say(msg.user_name, "К сожалению, никто не в сети для кражи.")
            return

        victim_id = secrets.choice(candidates)
        victim_name = handler._viewers[victim_id]["user_name"]
        victim_points = await handler.points.get_balance(victim_id)

        if victim_points < VICTIM_MIN_BALANCE:
            msg_text = random.choice(POOR_VICTIM_MESSAGES).format(name=victim_name)
            await handler._say(msg.user_name, msg_text)
        else:
            max_possible = max(0, victim_points - VICTIM_MIN_BALANCE)
            if max_possible < STEAL_AMOUNT_MIN:
                await handler._say(msg.user_name, "У жертвы почти ничего не осталось для кражи.")
            elif await has_steal_safe(handler._db, victim_id):
                msg_text = random.choice(SAFE_VICTIM_MESSAGES).format(name=victim_name)
                await handler._say(msg.user_name, msg_text)
                return
            else:
                stolen = random.randint(STEAL_AMOUNT_MIN, min(STEAL_AMOUNT_MAX, max_possible))
                await handler.steal.execute_steal(handler.points, uid, victim_id, stolen)
                await handler._say(
                    msg.user_name,
                    f"Успех! Тебе удалось украсть {stolen} принцесс у {victim_name}.",
                )

    chance_to_prison = prison_chance_for_amount(stolen)
    if chance_to_prison and random.randint(1, STEAL_ROLL_MAX) <= chance_to_prison:
        await handler.prison.imprison(uid)
        await handler.steal.increment_jail_count(uid)
        prison_minutes = PRISON_DURATION_SEC // 60
        await handler._say(msg.user_name, f"Тебя отправили в тюрьму на {prison_minutes} минут!")
