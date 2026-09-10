"""Обработчик: авто-ответы на !команды + фоновый цикл сообщений по таймеру.

Таймеры не копят очередь за время простоя: в БД хранится только `next_send_at`.
При старте просроченные таймеры переносятся на будущее (`now + interval`),
поэтому после рестарта бот ничего не досылает задним числом и не выплёскивает
накопленное одним пакетом. Пропущенные интервалы скипаются, не «навёрстываются».
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.db import messaging as messaging_db
from bot.goodgame import ChatMessage

log = logging.getLogger("messaging")

ReplyFn = Callable[[str], Awaitable[Optional[str]]]

# Максимальная пауза цикла таймеров (просыпаться ради правок из админки).
TICK_MAX_SEC = 30.0
# Разброс при перепланировании, чтобы сообщения не ходили строгими пачками.
JITTER_SEC = 5.0
# Пауза между отправками нескольких должников в одном тике (анти-флуд GG).
SEND_GAP_SEC = 4.0
# Разбег между таймерами, сброшенными при старте, поверх interval.
STARTUP_STAGGER_SEC = 3.0


class MessagingHandler:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._reply: Optional[ReplyFn] = None
        self._replies: dict[str, str] = {}
        self._timed_task: Optional[asyncio.Task] = None
        self._wake = asyncio.Event()

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    async def reload(self) -> None:
        """Перечитать включённые авто-ответы и разбудить цикл таймеров."""
        rows = await messaging_db.list_enabled_auto_responses(self._db)
        self._replies = {str(row["command"]): str(row["reply"]) for row in rows}
        self.wake()

    def wake(self) -> None:
        """Разбудить цикл таймеров (правки таймеров применяются сразу)."""
        self._wake.set()

    # --- Авто-ответы ---------------------------------------------------------

    async def handle_message(self, msg: ChatMessage) -> bool:
        """Ответить на админскую !команду. True — сообщение обработано."""
        if not self._replies:
            return False
        text = (msg.text or "").strip()
        if not text.startswith("!"):
            return False
        cmd = text.split(maxsplit=1)[0].lower()
        reply = self._replies.get(cmd)
        if reply is None:
            return False
        if self._reply is not None:
            try:
                await self._reply(reply)
            except Exception:  # noqa: BLE001
                log.exception("Авто-ответ %s не отправился", cmd)
        return True

    # --- Сообщения по таймеру ------------------------------------------------

    async def start(self) -> None:
        await self.reload()
        await self._reset_due_schedules()
        self._timed_task = asyncio.create_task(self._timed_loop())
        log.info("Messaging: авто-ответы (%d) и таймер-сообщения запущены.", len(self._replies))

    async def close(self) -> None:
        if self._timed_task:
            self._timed_task.cancel()
            try:
                await self._timed_task
            except asyncio.CancelledError:
                pass
            self._timed_task = None

    async def _reset_due_schedules(self) -> None:
        """Стартовая расстановка: просроченные таймеры — в будущее, без досыла."""
        now = time.time()
        rows = await messaging_db.list_enabled_timed_messages(self._db)
        reset_index = 0
        for row in rows:
            next_send_at = row["next_send_at"]
            if next_send_at is not None and next_send_at > now:
                continue  # будущий таймер после быстрого рестарта остаётся валидным
            reset_index += 1
            await messaging_db.set_timed_schedule(
                self._db,
                int(row["id"]),
                next_send_at=(
                    now
                    + int(row["interval_sec"])
                    + reset_index * STARTUP_STAGGER_SEC
                    + random.uniform(0.0, JITTER_SEC)
                ),
            )
        if reset_index:
            log.info(
                "Messaging: сброшено таймеров после рестарта: %d (без досыла).",
                reset_index,
            )

    async def _timed_loop(self) -> None:
        try:
            while True:
                delay = await self._next_wake_delay()
                self._wake.clear()
                try:
                    await asyncio.wait_for(
                        self._wake.wait(), timeout=max(1.0, min(TICK_MAX_SEC, delay))
                    )
                except asyncio.TimeoutError:
                    pass
                await self._send_due_messages()
        except asyncio.CancelledError:
            raise

    async def _next_wake_delay(self) -> float:
        rows = await messaging_db.list_enabled_timed_messages(self._db)
        now = time.time()
        upcoming = [
            float(row["next_send_at"]) - now
            for row in rows
            if row["next_send_at"] is not None and float(row["next_send_at"]) > now
        ]
        if len(upcoming) < len(rows):
            return 0.0  # есть должник или таймер без расписания
        if not upcoming:
            return TICK_MAX_SEC
        return min(TICK_MAX_SEC, max(1.0, min(upcoming)))

    async def _send_due_messages(self) -> None:
        rows = await messaging_db.list_enabled_timed_messages(self._db)
        now = time.time()
        due = [
            row
            for row in rows
            if row["next_send_at"] is None or float(row["next_send_at"]) <= now
        ]
        if not due:
            return
        for row in due:
            if self._reply is None:
                log.debug("Messaging: reply не привязан — сообщение #%s отложено", row["id"])
                return
            try:
                result = await self._reply(str(row["text"]))
            except Exception:  # noqa: BLE001
                log.exception("Таймер-сообщение #%s упало — повтор в следующем тике", row["id"])
                return
            if result is None:
                # Чат недоступен: не двигаем таймер, чтобы не «сжечь» интервал.
                log.warning("Таймер-сообщение #%s не доставлено — повтор позже", row["id"])
                return
            sent = time.time()
            await messaging_db.set_timed_schedule(
                self._db,
                int(row["id"]),
                last_sent_at=sent,
                next_send_at=sent + int(row["interval_sec"]) + random.uniform(0.0, JITTER_SEC),
            )
            if len(due) > 1:
                await asyncio.sleep(SEND_GAP_SEC)
