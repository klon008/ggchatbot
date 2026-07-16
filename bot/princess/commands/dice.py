from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

from bot.goodgame import ChatMessage

from ..settings import (
    DICE_COOLDOWN_SEC,
    DICE_COST,
    DICE_CRITICAL_FAIL,
    DICE_CRITICAL_FAIL_PENALTY,
    DICE_CRITICAL_SUCCESS,
    DICE_CRITICAL_SUCCESS_REWARD,
    DICE_ROLL_MAX,
    DICE_ROLL_MIN,
)

if TYPE_CHECKING:
    from bot.princess.handler import PrincessHandler


async def cmd_dice(handler: "PrincessHandler", msg: ChatMessage) -> None:
    uid = msg.user_id
    now = time.time()
    last = await handler.dice_cooldowns.get_last(uid)
    if now - last < DICE_COOLDOWN_SEC:
        await handler._say(msg.user_name, "Кубик можно бросать раз в 5 минут. Подожди немного!")
        return

    balance = await handler.points.get_balance(uid)
    if balance < DICE_COST:
        await handler._say(
            msg.user_name,
            f"У тебя недостаточно средств. Бросок стоит {DICE_COST} принцесс. Извини :(",
        )
        return

    await handler.points.add(uid, -DICE_COST)
    await handler.dice_cooldowns.set_last(uid, now)
    roll = random.randint(DICE_ROLL_MIN, DICE_ROLL_MAX)

    if roll == DICE_CRITICAL_FAIL:
        balance = await handler.points.get_balance(uid)
        await handler.points.set_balance(uid, max(0, balance - DICE_CRITICAL_FAIL_PENALTY))
        await handler._say(
            msg.user_name,
            f"{DICE_CRITICAL_FAIL}. Критический провал! С твоего баланса списаны "
            f"{DICE_CRITICAL_FAIL_PENALTY} принцесс. "
            "Любое получение принцесс остановлено на 5 минут",
        )
    elif roll == DICE_CRITICAL_SUCCESS:
        await handler.points.add(uid, DICE_CRITICAL_SUCCESS_REWARD)
        await handler._say(
            msg.user_name,
            f"{DICE_CRITICAL_SUCCESS}. Критический успех! Поздравляю, "
            f"тебе начислены {DICE_CRITICAL_SUCCESS_REWARD} принцесс",
        )
    else:
        await handler._say(msg.user_name, f"Бросок кубика: выпало {roll}")
