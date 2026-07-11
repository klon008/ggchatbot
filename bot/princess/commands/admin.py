from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from bot.goodgame import ChatMessage

if TYPE_CHECKING:
    from bot.princess.handler import PrincessHandler


async def cmd_admin_points(handler: "PrincessHandler", msg: ChatMessage) -> None:
    if not handler.admin_user_id or msg.user_id != handler.admin_user_id:
        await handler._say(msg.user_name, "Только администратор может списывать/начислить баллы")
        return

    parts = msg.text.split()
    if len(parts) != 3:
        await handler._say(
            msg.user_name,
            "Используйте формат: !списать/начислить никнейм количество",
        )
        return

    command = parts[0].lower()
    target_nick = parts[1]
    try:
        amount = int(parts[2])
    except ValueError:
        await handler._say(msg.user_name, "Количество должно быть числом")
        return

    target_uid: Optional[str] = None
    target_name: Optional[str] = None
    for vuid, data in handler._viewers.items():
        if data["user_name"].lower() == target_nick.lower():
            target_uid = vuid
            target_name = data["user_name"]
            break

    if target_uid is None or target_name is None:
        await handler._say(msg.user_name, f"Пользователь '{target_nick}' не найден в чате.")
        return

    balance = await handler.points.get_balance(target_uid)
    if command == "!начислить":
        await handler.points.set_balance(target_uid, balance + amount)
        await handler._say(msg.user_name, f"{amount} принцесс были начислены {target_name}")
    elif command == "!списать":
        await handler.points.set_balance(target_uid, max(0, balance - amount))
        await handler._say(msg.user_name, f"{amount} принцесс были списаны со счета {target_name}")
    else:
        await handler._say(msg.user_name, "Неверная команда.")
