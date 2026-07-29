"""Обработчик princess-команд и пассивного дохода в чате."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
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
from .economy import is_steal_schedule_day, now_msk
from .prison import PrisonManager
from .settings import MESSAGE_POINTS, PASSIVE_INCOME_INTERVAL_SEC, PASSIVE_INCOME_PER_MIN
from .storage import DailyStore, DiceCooldownStore, StealStore, next_steal_weekday_label

log = logging.getLogger("princess")

ReplyFn = Callable[[str, str], Awaitable[None]]
AnnounceFn = Callable[[str], Awaitable[Optional[str]]]
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
        self._steal_watch_task: Optional[asyncio.Task] = None
        self._steal_wake = asyncio.Event()
        self._reply: Optional[ReplyFn] = None
        self._announce: Optional[AnnounceFn] = None
        self._fetch_viewers: Optional[ViewersFetchFn] = None
        self._last_schedule_was_open: Optional[bool] = None

    async def start(self) -> None:
        await self.points.load()
        await self.steal.load()
        await self.daily.load()
        await self.daily.normalize()
        self._last_schedule_was_open = is_steal_schedule_day()
        self._tick_task = asyncio.create_task(self._passive_income_loop())
        self._steal_watch_task = asyncio.create_task(self._steal_watch_loop())
        log.info("Princess-модуль запущен.")

    async def close(self) -> None:
        await self.points.flush()
        for task in (self._tick_task, self._steal_watch_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_announce(self, announce: AnnounceFn) -> None:
        self._announce = announce

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

    async def get_steal_status(self) -> dict:
        return await self.steal.get_status()

    async def admin_steal_open(self, duration_hours: Optional[float] = None) -> dict:
        """Открыть кражу вручную. duration_hours=None — бессрочно до закрытия."""
        if duration_hours is not None:
            if duration_hours <= 0:
                raise ValueError("duration_hours must be > 0")
            until = time.time() + duration_hours * 3600
            await self.steal.set_override(enabled=False, until=until)
            hours_label = (
                str(int(duration_hours))
                if float(duration_hours).is_integer()
                else f"{duration_hours:g}"
            )
            await self._announce_chat(
                f"Кража открыта на {hours_label} ч! Команда !кража доступна."
            )
        else:
            await self.steal.set_override(enabled=True, until=None)
            await self._announce_chat("Кража открыта вручную! Команда !кража доступна.")
        self._steal_wake.set()
        return await self.steal.get_status()

    async def admin_steal_close(self) -> dict:
        """Сбросить ручной override. По расписанию ср/пт кража остаётся доступной."""
        was_override = False
        meta = await self.steal.get_meta()
        now = time.time()
        if meta["override_enabled"]:
            was_override = True
        elif meta["override_until"] is not None and meta["override_until"] > now:
            was_override = True
        await self.steal.clear_override()
        if was_override and not is_steal_schedule_day():
            await self._announce_chat("Кража закрыта.")
        self._steal_wake.set()
        return await self.steal.get_status()

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

    async def _steal_watch_loop(self) -> None:
        try:
            while True:
                await self._steal_process_events()
                delay = await self._steal_next_wake_delay()
                meta = await self.steal.get_meta()
                today_key = now_msk().strftime("%Y-%m-%d")
                # Пока GG не подключён, анонс дня кражи не дойдёт — короткий retry.
                if (
                    is_steal_schedule_day()
                    and meta["last_schedule_open_key"] != today_key
                ):
                    delay = min(delay, 15.0)
                self._steal_wake.clear()
                try:
                    await asyncio.wait_for(
                        self._steal_wake.wait(), timeout=max(1.0, delay)
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise

    async def _steal_next_wake_delay(self) -> float:
        now = time.time()
        next_midnight = self._seconds_until_next_msk_midnight()
        delays = [next_midnight]
        meta = await self.steal.get_meta()
        until = meta["override_until"]
        if until is not None and until > now:
            delays.append(until - now)
        return min(delays)

    @staticmethod
    def _seconds_until_next_msk_midnight() -> float:
        now = now_msk()
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return max(1.0, (tomorrow - now).total_seconds())

    async def _steal_process_events(self) -> None:
        cleared = await self.steal.clear_expired_timer()
        if cleared:
            meta = await self.steal.get_meta()
            if not meta["override_enabled"] and not is_steal_schedule_day():
                await self._announce_chat("Кража закрыта.")

        schedule_open = is_steal_schedule_day()
        today_key = now_msk().strftime("%Y-%m-%d")
        meta = await self.steal.get_meta()

        if schedule_open and meta["last_schedule_open_key"] != today_key:
            ok = await self._announce_chat(
                "Сегодня день кражи! Команда !кража доступна до конца суток (МСК)."
            )
            if ok:
                await self.steal.set_schedule_open_key(today_key)
        elif (
            self._last_schedule_was_open
            and not schedule_open
            and not meta["override_enabled"]
            and not (
                meta["override_until"] is not None and meta["override_until"] > time.time()
            )
        ):
            nxt = next_steal_weekday_label()
            await self._announce_chat(f"День кражи закончился. Следующий — {nxt}.")

        self._last_schedule_was_open = schedule_open

    async def _announce_chat(self, text: str) -> bool:
        if self._announce is None:
            log.debug("Princess announce (no channel): %s", text)
            return False
        try:
            result = await self._announce(text)
            return result is not None
        except Exception:  # noqa: BLE001
            log.exception("Не удалось отправить анонс кражи в чат.")
            return False

    async def _say(self, user_name: str, text: str) -> None:
        if self._reply is None:
            log.debug("Princess (no reply): %s, %s", user_name, text)
            return
        await self._reply(user_name, text)