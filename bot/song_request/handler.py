"""Song-request: очередь YouTube, OBS-плеер, команды заказа музыки."""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.db import queue as queue_db
from bot.economy import PointsStore, pluralize_princess
from bot.goodgame import ChatMessage
from bot.web import LocalWebServer
from bot.web.routes.player import PlayerRoutes
from config import Config

from .playback import PlaybackController
from .queue import QueueManager, Track
from .settings import SR_COST
from .youtube import canonical_url, validate_request

log = logging.getLogger("song_request")

ReplyFn = Callable[[str], Awaitable[None]]

_ORDER_CMDS = ("!заказ", "!зм", "!sr")
_SKIP_CMDS = ("!пропуск", "!skip")
_QUEUE_CMDS = ("!очередь",)
_NOW_CMDS = ("!играет", "!сейчас")


class SongRequestHandler:
    def __init__(self, cfg: Config, db: Database, web: LocalWebServer) -> None:
        self.cfg = cfg
        self._db = db
        self.queue = QueueManager(db, max_size=cfg.max_queue_size)
        self.player = PlayerRoutes(on_status=self._on_obs_status)
        self.player.register(web.app)
        self.playback = PlaybackController(
            cfg=cfg,
            queue=self.queue,
            player=self.player,
            points_getter=lambda: self._points,
            say=self._say,
        )
        self._cooldowns: dict[str, float] = {}
        self._reply: Optional[ReplyFn] = None
        self._points: Optional[PointsStore] = None
        self._orders_enabled = True

    async def start(self) -> None:
        await self.queue.load()
        self._orders_enabled = await queue_db.get_orders_enabled(self._db)
        log.info("Song-request модуль запущен (заказы: %s).", "вкл" if self._orders_enabled else "выкл")

    async def close(self) -> None:
        await self.playback.close()
        await self.player.close()

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    @property
    def orders_enabled(self) -> bool:
        return self._orders_enabled

    @property
    def player_paused(self) -> bool:
        return self.playback.player_paused

    async def toggle_pause(self) -> bool:
        if not self.queue.is_playing:
            raise RuntimeError("nothing_playing")
        self.playback.player_paused = not self.playback.player_paused
        if self.playback.player_paused:
            self.playback.cancel_watchdog()
        else:
            self.playback.arm_watchdog(self.queue.current_token)
        await self.player.send_toggle_pause(self.queue.current_token)
        return self.playback.player_paused

    async def set_orders_enabled(self, enabled: bool) -> None:
        if enabled == self._orders_enabled:
            return
        await queue_db.set_orders_enabled(self._db, enabled)
        self._orders_enabled = enabled
        if not enabled:
            refunded = await self.playback.clear_queue_with_refunds()
            if refunded > 0:
                await self._say(
                    "Заказы музыки отключены. Очередь очищена, принцессы возвращены."
                )
            else:
                await self._say("Заказы музыки отключены. Очередь очищена.")
        else:
            log.info("Заказы музыки включены.")
            await self._say("Заказы музыки снова доступны.")

    async def handle_message(self, msg: ChatMessage) -> bool:
        text = msg.text.strip()
        if not text.startswith("!"):
            return False

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in _ORDER_CMDS:
            await self._cmd_sr(msg, arg)
        elif cmd in _SKIP_CMDS:
            await self._cmd_skip(msg)
        elif cmd in _QUEUE_CMDS:
            await self._cmd_queue(msg)
        elif cmd in _NOW_CMDS:
            await self._cmd_song(msg)
        else:
            return False

        return True

    async def advance(self, expected_token: Optional[str], skip_reason: Optional[str] = None) -> None:
        await self.playback.advance(expected_token, skip_reason)

    async def _on_obs_status(self, data: dict) -> None:
        await self.playback.on_obs_status(data)

    async def _cmd_sr(self, msg: ChatMessage, arg: str) -> None:
        try:
            await self._cmd_sr_inner(msg, arg)
        except Exception:  # noqa: BLE001
            log.exception("Ошибка обработки заказа от %s", msg.user_name)
            try:
                await self._say(
                    f"{msg.user_name}, не удалось оформить заказ — попробуй позже"
                )
            except Exception:  # noqa: BLE001
                pass

    async def _cmd_sr_inner(self, msg: ChatMessage, arg: str) -> None:
        if not self._orders_enabled:
            await self._say(f"{msg.user_name}, заказ песен временно отключён")
            return

        if not self.playback.youtube_available:
            await self._say(
                f"{msg.user_name}, плеер не может подключиться к YouTube — "
                "заказ сейчас недоступен"
            )
            return

        if self.cfg.user_cooldown_sec > 0:
            last = self._cooldowns.get(msg.user_id, 0.0)
            wait = self.cfg.user_cooldown_sec - (time.time() - last)
            if wait > 0:
                await self._say(f"{msg.user_name}, подожди ещё {int(wait) + 1}с перед следующим заказом")
                return

        if self.queue.is_full():
            await self._say(f"{msg.user_name}, очередь заполнена ({self.cfg.max_queue_size})")
            return

        result = validate_request(arg)
        if not result.ok:
            await self._say(f"{msg.user_name}, {result.reason}")
            return

        if SR_COST > 0:
            if self._points is None:
                await self._say(f"{msg.user_name}, заказ песен временно недоступен")
                return
            balance = await self._points.get_balance(msg.user_id)
            if balance < SR_COST:
                await self._say(
                    f"{msg.user_name}, недостаточно принцесс: "
                    f"нужно {SR_COST}, у тебя {balance} {pluralize_princess(balance)}"
                )
                return
            await self._points.add(msg.user_id, -SR_COST)

        track = Track(
            video_id=result.video_id,
            requested_by=msg.user_id,
            requested_by_name=msg.user_name,
            url=canonical_url(result.video_id),
            title="",
            paid_cost=SR_COST if SR_COST > 0 else 0,
        )
        position = await self.queue.add(track)
        self._cooldowns[msg.user_id] = time.time()
        if SR_COST > 0:
            await self._say(
                f"{msg.user_name}, добавлено в очередь (#{position}), "
                f"списано {SR_COST} {pluralize_princess(SR_COST)}"
            )
        else:
            await self._say(f"{msg.user_name}, добавлено в очередь (#{position})")

        if not self.queue.is_playing:
            await self.advance(expected_token=None)

    async def _cmd_skip(self, msg: ChatMessage) -> None:
        if not msg.is_moderator:
            await self._say(f"{msg.user_name}, команда !пропуск доступна только модераторам")
            return
        if not self.queue.is_playing:
            await self._say("Сейчас ничего не играет")
            return
        await self.player.send_skip(self.queue.current_token)
        await self._say(f"{msg.user_name} пропустил трек")
        if not self.player.has_clients:
            await self.queue.force_skip()
            await self.advance(expected_token=None)

    async def _cmd_queue(self, msg: ChatMessage) -> None:
        upcoming = self.queue.upcoming(3)
        if not upcoming and not self.queue.is_playing:
            await self._say("Очередь пуста")
            return
        parts = [f"в очереди: {len(self.queue)}"]
        if upcoming:
            ids = ", ".join(t.video_id for t in upcoming)
            parts.append(f"далее: {ids}")
        await self._say(" • ".join(parts))

    async def _cmd_song(self, msg: ChatMessage) -> None:
        if self.queue.current:
            cur = self.queue.current
            who = cur.requested_by_name or cur.requested_by
            label = cur.title or cur.url
            await self._say(f"сейчас играет: {who} — {label}")
        else:
            await self._say("сейчас ничего не играет")

    async def _say(self, text: str) -> None:
        if self._reply:
            await self._reply(text)
