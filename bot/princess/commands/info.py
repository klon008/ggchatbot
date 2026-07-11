from __future__ import annotations

import random
from typing import TYPE_CHECKING

from bot.economy import pluralize_princess
from bot.goodgame import ChatMessage
from bot.princesses import DISNEY_PRINCESSES

from ..economy import update_chance

if TYPE_CHECKING:
    from bot.princess.handler import PrincessHandler


async def cmd_srok(handler: "PrincessHandler", msg: ChatMessage) -> None:
    await handler._say(msg.user_name, await handler.prison.format_srok(msg.user_id))


async def cmd_points(handler: "PrincessHandler", msg: ChatMessage) -> None:
    count = await handler.points.get_balance(msg.user_id)
    await handler._say(msg.user_name, f"У тебя: {count} {pluralize_princess(count)}")


async def cmd_neuro(handler: "PrincessHandler", msg: ChatMessage) -> None:
    await handler._say(
        msg.user_name,
        "Здесь стример создаёт своих принцесс: "
        "https://shedevrum.ai/@dartval?share=444jmjdeffe2b8k8w14vq8c350",
    )


async def cmd_sound(handler: "PrincessHandler", msg: ChatMessage) -> None:
    await handler._say(
        msg.user_name,
        "Доступные звуковые команды: нифига, даблин, незнаю, поновой, сколько, "
        "смех, прыгай, жаль, тяжело, скандал, окэй, беги, верю, протест, "
        "видно, хорошо, супер, ашалеть, кря",
    )


async def cmd_disney(handler: "PrincessHandler", msg: ChatMessage) -> None:
    princess = random.choice(DISNEY_PRINCESSES)
    await handler._say(
        msg.user_name,
        f"Какая принцесса Диснея ты сегодня? Сегодня ты - {princess}!",
    )


async def cmd_collection(handler: "PrincessHandler", msg: ChatMessage) -> None:
    await handler._say(msg.user_name, "Обзор коллекции стримера: https://youtu.be/UBJuIAMbW_I")


async def cmd_pocket(handler: "PrincessHandler", msg: ChatMessage) -> None:
    async with handler.steal.mutate_info(msg.user_id) as data:
        update_chance(data)
        attempts = data["attempts"]
        successes = data["success"]
        total_stolen = data.get("stolen_total", 0)
        chance = data["chance"]
        times_in_jail = data.get("times_in_jail", 0)

    await handler._say(
        msg.user_name,
        "твоя статистика:\n"
        f"Попыток: {attempts}\n"
        f"Успехов: {successes}\n"
        f"Всего украдено принцесс: {total_stolen}\n"
        f"Количество отсидок: {times_in_jail}\n"
        f"Текущий шанс кражи: {chance}%",
    )
