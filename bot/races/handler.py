"""Обработчик команд !забег."""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.economy.points import PointsStore
from bot.goodgame import ChatMessage

from . import bets
from .bets import (
    RACE_ADMIN_BANK_CMD,
    RACE_ADMIN_RESET_CMD,
    RACE_ADMIN_TOPUP_CMD,
    RACE_CMD,
    RACE_RULES_CMD,
)
from .round import RoundManager

log = logging.getLogger("races")

ReplyFn = Callable[[str], Awaitable[Optional[str]]]
RemoveFn = Callable[[str], Awaitable[None]]


class RacesHandler:
    def __init__(self, db: Database, admin_user_id: str) -> None:
        self._db = db
        self.admin_user_id = str(admin_user_id)
        self.rounds = RoundManager(db)
        self._reply: Optional[ReplyFn] = None

    async def start(self) -> None:
        await self.rounds.start()
        log.info("Races модуль запущен.")

    async def close(self) -> None:
        await self.rounds.close()

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply
        self.rounds.bind_say(reply)

    def bind_remove(self, remove: RemoveFn) -> None:
        self.rounds.bind_remove(remove)

    def bind_points(self, store: PointsStore) -> None:
        self.rounds.bind_points(store)

    async def get_status(self) -> dict:
        return await self.rounds.status_snapshot()

    async def set_auto_enabled(self, enabled: bool) -> None:
        await self.rounds.set_auto_enabled(enabled)

    async def set_timers(
        self,
        collect_sec: int,
        cooldown_sec: int,
        race_delay_sec: Optional[int] = None,
    ) -> None:
        await self.rounds.set_timers(collect_sec, cooldown_sec, race_delay_sec)

    async def admin_open(self) -> None:
        await self.rounds.admin_open()

    async def admin_start(self) -> None:
        await self.rounds.admin_start()

    async def admin_cancel(self) -> None:
        await self.rounds.admin_cancel()

    async def admin_top_up_bank(self, amount: int) -> int:
        return await self.rounds.top_up_bank(amount)

    async def admin_reset_bank(self) -> int:
        return await self.rounds.reset_bank()

    async def handle_message(self, msg: ChatMessage) -> bool:
        text = msg.text.strip()
        lower = text.lower()

        if lower == RACE_RULES_CMD:
            await self._say(bets.RULES_TEXT)
            return True

        cmd = lower.split(maxsplit=1)[0] if lower.startswith("!") else ""

        if cmd == RACE_ADMIN_BANK_CMD:
            if str(msg.user_id) != self.admin_user_id:
                return False
            bank = await self.rounds.get_bank()
            await self._say(f"Казна мини-игр: {bank} баллов.")
            return True

        if cmd == RACE_ADMIN_TOPUP_CMD:
            if str(msg.user_id) != self.admin_user_id:
                return False
            parts = text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip().isdigit():
                await self._say(f"Формат: {RACE_ADMIN_TOPUP_CMD} <сумма>")
                return True
            amount = int(parts[1].strip())
            if amount <= 0:
                await self._say("Сумма должна быть больше нуля.")
                return True
            new_bank = await self.rounds.top_up_bank(amount)
            await self._say(f"Казна пополнена на {amount}. Баланс: {new_bank} баллов.")
            return True

        if cmd == RACE_ADMIN_RESET_CMD:
            if str(msg.user_id) != self.admin_user_id:
                return False
            new_bank = await self.rounds.reset_bank()
            await self._say(f"Казна сброшена: {new_bank} баллов.")
            return True

        if lower == RACE_CMD:
            err = await self.rounds.open_from_chat(msg.user_name)
            if err:
                await self._say(f"{msg.user_name}, {err}")
            return True

        if not lower.startswith(RACE_CMD):
            return False

        parsed = bets.parse_bet_command(text)
        if isinstance(parsed, bets.ParseError):
            await self._say(f"{msg.user_name}, {parsed.message}")
            return True

        err = await self.rounds.place_bet(msg.user_id, msg.user_name, parsed)
        if err:
            if err.startswith(msg.user_name):
                await self._say(err)
            else:
                await self._say(f"{msg.user_name}, {err}")
        return True

    async def _say(self, text: str) -> None:
        if self._reply is not None:
            await self._reply(text)
        else:
            log.info("races (no reply): %s", text)
