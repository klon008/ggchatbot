from __future__ import annotations

from typing import TYPE_CHECKING

from bot.goodgame import ChatMessage

from ..economy import get_daily_bonus, now_msk

if TYPE_CHECKING:
    from bot.princess.handler import PrincessHandler


async def cmd_daily(handler: "PrincessHandler", msg: ChatMessage) -> None:
    if msg.text.strip().lower() != "!дейлик":
        return

    today = now_msk()
    today_str = today.strftime("%Y-%m-%d")
    current_month = today.strftime("%Y-%m")
    uid = msg.user_id

    async with handler.daily.mutate() as data:
        if data.get("current_month") != current_month:
            data["current_month"] = current_month
            data["user_progress"] = {}

        if today_str in data and uid in data[today_str]:
            await handler._say(msg.user_name, "Тебе уже начислен ежедневный бонус сегодня!")
            return

        counter = data["user_progress"].get(uid, 0) + 1
        bonus = get_daily_bonus(counter)
        data["user_progress"][uid] = counter
        data.setdefault(today_str, [])
        if uid not in data[today_str]:
            data[today_str].append(uid)

    await handler.points.add(uid, bonus)
    await handler._say(msg.user_name, f"Тебе начислен ежедневный бонус {bonus} принцесс!")
