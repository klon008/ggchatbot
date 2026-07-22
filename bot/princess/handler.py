"""Обработчик princess-команд и пассивного дохода в чате."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from bot.economy import PointsStore
from bot.goodgame import ChatMessage

from bot.db import Database
from bot.db import prison as prison_db

from .commands import (
    cmd_admin_points,
    cmd_collection,
    cmd_daily,
    cmd_dice,
    cmd_disney,
    cmd_neuro,
    cmd_points,
    cmd_pocket,
    cmd_sound,
    cmd_srok,
    cmd_steal,
)
from .prison import PrisonManager
from .settings import MESSAGE_POINTS, PASSIVE_INCOME_INTERVAL_SEC, PASSIVE_INCOME_PER_MIN
from .storage import DailyStore, DiceCooldownStore, StealStore

log = logging.getLogger("princess")

ReplyFn = Callable[[str, str], Awaitable[None]]
ViewersFetchFn = Callable[[], Awaitable[list[dict]]]


class PrincessHandler:
    """Игровая экономика принцесс — команды, пассивный доход, тюрьма."""

    def __init__(self, db: Database, admin_user_id: str, bot_user_id: str = "") -> None:
        self._db = db
        self.admin_user_id = str(admin_user_id).strip()
        self._bot_user_id = str(bot_user_id).strip()
        self.points = PointsStore(db)
        self.steal = StealStore(db)
        self.daily = DailyStore(db)
        self.prison = PrisonManager(db)
        self.dice_cooldowns = DiceCooldownStore(db)
        self._viewers: dict[str, dict] = {}
        self._tick_task: Optional[asyncio.Task] = None
        self._reply: Optional[ReplyFn] = None
        self._fetch_viewers: Optional[ViewersFetchFn] = None

    async def start(self) -> None:
        await self.points.load()
        await self.steal.load()
        await self.daily.load()
        await self.daily.normalize()
        self._tick_task = asyncio.create_task(self._passive_income_loop())
        log.info("Princess-модуль запущен.")

    async def close(self) -> None:
        await self.points.flush()
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_viewers_fetch(self, fetch: ViewersFetchFn) -> None:
        self._fetch_viewers = fetch

    def sync_viewers(self, users: list[dict]) -> None:
        """Заменить список зрителей данными из get_users_list2."""
        now = time.time()
        new_viewers: dict[str, dict] = {}
        for user in users:
            uid = str(user.get("id", ""))
            if not uid or uid == "0":
                continue
            if self._bot_user_id and uid == self._bot_user_id:
                continue
            new_viewers[uid] = {
                "user_name": str(user.get("name", "")),
                "last_active": self._viewers.get(uid, {}).get("last_active", now),
            }
        self._viewers = new_viewers

    async def _refresh_viewers(self) -> bool:
        if self._fetch_viewers is None:
            log.warning("fetch_viewers не привязан — пропуск синхронизации зрителей.")
            return False
        try:
            users = await self._fetch_viewers()
        except Exception:  # noqa: BLE001
            log.warning("Не удалось получить список зрителей.", exc_info=True)
            return False
        self.sync_viewers(users)
        log.debug("Список зрителей обновлён: %d человек.", len(self._viewers))
        return True

    async def handle_message(self, msg: ChatMessage) -> bool:
        """Обработать сообщение. True — princess-команда обработана (SR не нужен)."""
        text = msg.text.strip()
        user_id = msg.user_id
        user_name = msg.user_name

        cmd = text.split(maxsplit=1)[0].lower() if text.startswith("!") else ""

        await self.points.touch_name(user_id, user_name)

        if await self.prison.is_in_prison(user_id):
            # Узник изолирован от остальных фич (SR, карты, …); доступна только !срок.
            if cmd == "!срок":
                await cmd_srok(self, msg)
            elif cmd.startswith("!"):
                await self._say(user_name, "ты в тюрьме. Доступна команда !срок")
            return True

        if not text.startswith("!"):
            await self.points.add(user_id, MESSAGE_POINTS)
            return False

        handlers = {
            "!срок": cmd_srok,
            "!кража": cmd_steal,
            "!нейро": cmd_neuro,
            "!звук": cmd_sound,
            "!дайс": cmd_dice,
            "!дисней": cmd_disney,
            "!баллы": cmd_points,
            "!карман": cmd_pocket,
            "!коллекция": cmd_collection,
            "!дейлик": cmd_daily,
        }

        if cmd in handlers:
            await handlers[cmd](self, msg)
            return True

        if cmd in ("!списать", "!начислить"):
            await cmd_admin_points(self, msg)
            return True

        return False

    async def _passive_income_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(PASSIVE_INCOME_INTERVAL_SEC)
                if not await self._refresh_viewers():
                    continue
                eligible = await prison_db.filter_eligible(
                    self._db, list(self._viewers.keys())
                )
                await self.points.apply_income_tick(eligible, PASSIVE_INCOME_PER_MIN)
        except asyncio.CancelledError:
            raise

    async def _say(self, user_name: str, text: str) -> None:
        if self._reply is None:
            log.debug("Princess (no reply): %s, %s", user_name, text)
            return
        await self._reply(user_name, text)
