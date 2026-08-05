"""Анонс смены суток: хуки модулей + первое сообщение / tick у полуночи МСК."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Optional, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from bot.db import Database
from bot.db import daycycle as daycycle_db
from bot.goodgame import ChatMessage

log = logging.getLogger("daycycle")

MSK = ZoneInfo("Europe/Moscow")

ReplyFn = Callable[[str], Awaitable[Optional[str]]]


@dataclass(frozen=True)
class DayCtx:
    today: str
    previous: str


@runtime_checkable
class DayHook(Protocol):
    async def on_new_day(self, ctx: DayCtx) -> list[str]:
        """Вернуть 0..N фраз для общего анонса смены суток."""


def day_key(dt: datetime | None = None) -> str:
    return (dt or datetime.now(MSK)).strftime("%Y-%m-%d")


def seconds_until_next_msk_midnight() -> float:
    now = datetime.now(MSK)
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1.0, (tomorrow - now).total_seconds())


class DaycycleHandler:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._hooks: list[DayHook] = []
        self._reply: Optional[ReplyFn] = None
        self._tick_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def add_hook(self, hook: DayHook) -> None:
        self._hooks.append(hook)

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    async def start(self) -> None:
        await daycycle_db.ensure_meta(self._db)
        self._tick_task = asyncio.create_task(self._midnight_loop())
        log.info("Daycycle: координатор анонса суток запущен.")

    async def close(self) -> None:
        if self._tick_task:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None

    async def on_chat_message(self, msg: ChatMessage) -> None:
        await self.maybe_announce()

    async def maybe_announce(self) -> None:
        async with self._lock:
            await self._maybe_announce_unlocked()

    async def _maybe_announce_unlocked(self) -> None:
        today = day_key()
        previous = await daycycle_db.get_announced_day_key(self._db)
        if previous == today:
            return

        if not previous:
            # Первый запуск / нет смены суток — только зафиксировать день.
            await daycycle_db.set_announced_day_key(self._db, today)
            log.info("Daycycle: seed announced_day_key=%s (без анонса)", today)
            return

        ctx = DayCtx(today=today, previous=previous)
        parts: list[str] = []
        for hook in self._hooks:
            try:
                chunk = await hook.on_new_day(ctx)
            except Exception:  # noqa: BLE001
                log.exception("Daycycle: on_new_day failed for %s", type(hook).__name__)
                continue
            if not chunk:
                continue
            for item in chunk:
                text = str(item or "").strip()
                if text:
                    parts.append(text)

        message = " ".join(parts)
        if message:
            if self._reply is None:
                log.debug("Daycycle announce (no channel): %s", message)
                return
            try:
                result = await self._reply(message)
            except Exception:  # noqa: BLE001
                log.exception("Daycycle: не удалось отправить анонс суток")
                return
            if result is None:
                log.warning("Daycycle: анонс не доставлен, повтор позже")
                return

        await daycycle_db.set_announced_day_key(self._db, today)
        for hook in self._hooks:
            on_announced = getattr(hook, "on_day_announced", None)
            if on_announced is None:
                continue
            try:
                await on_announced(ctx)
            except Exception:  # noqa: BLE001
                log.exception(
                    "Daycycle: on_day_announced failed for %s",
                    type(hook).__name__,
                )
        if message:
            log.info("Daycycle: анонс суток %s → %s", previous, today)
        else:
            log.info("Daycycle: смена суток %s → %s (пустой анонс)", previous, today)

    async def _midnight_loop(self) -> None:
        try:
            while True:
                delay = seconds_until_next_msk_midnight()
                await asyncio.sleep(delay)
                # Небольшой запас после полуночи, чтобы weekday/day_key стабилизировались.
                await asyncio.sleep(1.0)
                await self.maybe_announce()
        except asyncio.CancelledError:
            raise
