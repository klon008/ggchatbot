"""Обработчик команд !опрос."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.economy.points import PointsStore
from bot.goodgame import ChatMessage

from .round import RoundManager
from .settings import POLL_CMD, POLL_MIN_STAKE

log = logging.getLogger("polls")

ReplyFn = Callable[[str], Awaitable[None]]

RULES_TEXT = (
    "Опрос (прогноз): ставка за баллы принцесс на вариант. "
    f"Формат: {POLL_CMD} <сумма> <номер варианта> (мин. {POLL_MIN_STAKE}). "
    "После закрытия стример выбирает победителя — победители делят банк проигравших. "
    "Отмена опроса — полный возврат всем. "
    f"Статус: {POLL_CMD}"
)


class PollsHandler:
    def __init__(self, db: Database) -> None:
        self._db = db
        self.rounds = RoundManager(db)
        self._reply: Optional[ReplyFn] = None

    async def start(self) -> None:
        await self.rounds.start()
        log.info("Polls модуль запущен.")

    async def close(self) -> None:
        await self.rounds.close()

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply
        self.rounds.bind_say(reply)

    def bind_points(self, store: PointsStore) -> None:
        self.rounds.bind_points(store)

    async def get_status(self) -> dict:
        return await self.rounds.status_snapshot()

    async def admin_create(self, title: str, options: list[str], collect_sec: int) -> None:
        await self.rounds.admin_create(title, options, collect_sec)

    async def admin_lock(self) -> None:
        await self.rounds.admin_lock()

    async def admin_resolve(self, option_index: int) -> None:
        await self.rounds.admin_resolve(option_index)

    async def admin_cancel(self) -> None:
        await self.rounds.admin_cancel()

    async def handle_message(self, msg: ChatMessage) -> bool:
        text = msg.text.strip()
        lower = text.lower()

        if lower == f"{POLL_CMD} правила":
            await self._say(RULES_TEXT)
            return True

        if not lower.startswith(POLL_CMD):
            return False

        rest = text[len(POLL_CMD) :].strip()
        if not rest:
            snap = await self.rounds.status_snapshot()
            await self._say(self.rounds.format_status_chat(snap))
            return True

        parts = rest.split()
        if len(parts) < 2:
            await self._say(
                f"{msg.user_name}, формат: {POLL_CMD} <сумма> <номер варианта>"
            )
            return True

        amount_raw, option_raw = parts[0], parts[1]
        if not amount_raw.isdigit() or not option_raw.isdigit():
            await self._say(
                f"{msg.user_name}, формат: {POLL_CMD} <сумма> <номер варианта>"
            )
            return True

        amount = int(amount_raw)
        option_num = int(option_raw)
        if amount <= 0 or option_num <= 0:
            await self._say(f"{msg.user_name}, сумма и номер должны быть > 0")
            return True

        err = await self.rounds.place_bet(
            msg.user_id,
            msg.user_name,
            amount,
            option_num - 1,
        )
        if err:
            await self._say(f"{msg.user_name}, {err}")
            return True

        snap = await self.rounds.status_snapshot()
        opts = snap.get("options") or []
        label = ""
        if 0 <= option_num - 1 < len(opts):
            label = opts[option_num - 1].get("label", str(option_num))
        else:
            label = str(option_num)
        await self._say(f"{msg.user_name}, ставка {amount} на «{label}» принята!")
        return True

    async def _say(self, text: str) -> None:
        if self._reply is not None:
            await self._reply(text)
        else:
            log.info("polls (no reply): %s", text)
