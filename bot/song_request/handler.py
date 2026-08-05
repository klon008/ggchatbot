"""Song-request: очередь YouTube/ЯМузыка, OBS-плеер, команды заказа музыки."""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.db import queue as queue_db
from bot.db.connection import DATA_DIR
from bot.economy import PointsStore, pluralize_princess
from bot.goodgame import ChatMessage
from bot.web import LocalWebServer
from bot.web.routes.player import PlayerRoutes
from config import Config

from .playback import PlaybackController
from .queue import PROVIDER_YANDEX, PROVIDER_YOUTUBE, QueueManager, Track
from .settings import SR_COST
from .validate import validate_order
from .yandex_stream import YandexStreamService

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
        self.ym_stream = YandexStreamService(
            cfg.yandex_music_token,
            DATA_DIR / "ym_cache",
        )
        self.player = PlayerRoutes(on_status=self._on_obs_status, ym_stream=self.ym_stream)
        self.player.register(web.app)
        self.playback = PlaybackController(
            cfg=cfg,
            queue=self.queue,
            player=self.player,
            points_getter=lambda: self._points,
            say=self._say,
            ym_stream=self.ym_stream,
        )
        self._cooldowns: dict[str, float] = {}
        self._reply: Optional[ReplyFn] = None
        self._points: Optional[PointsStore] = None
        self._orders_enabled = True
        self._block_ym_explicit = True
        self._sr_cost = SR_COST

    async def start(self) -> None:
        await self.queue.load()
        self._orders_enabled = await queue_db.get_orders_enabled(self._db)
        self._block_ym_explicit = await queue_db.get_block_ym_explicit(self._db)
        self.ym_stream.set_block_explicit(self._block_ym_explicit)
        await self._load_queue_limits()
        ym = "вкл" if self.ym_stream.configured else "выкл (нет YANDEX_MUSIC_TOKEN)"
        log.info(
            "Song-request модуль запущен (заказы: %s, ЯМузыка: %s, block_explicit: %s, "
            "queue=%s, max_dur=%ss, watchdog_extra=%ss, cooldown=%ss, sr_cost=%s).",
            "вкл" if self._orders_enabled else "выкл",
            ym,
            "вкл" if self._block_ym_explicit else "выкл",
            self.cfg.max_queue_size,
            self.cfg.max_duration_sec,
            self.cfg.track_watchdog_extra_sec,
            self.cfg.user_cooldown_sec,
            self._sr_cost,
        )

    async def _load_queue_limits(self) -> None:
        stored = await queue_db.get_queue_limits(self._db)
        seed: dict[str, int] = {}
        defaults = {
            "max_queue_size": self.cfg.max_queue_size,
            "max_duration_sec": self.cfg.max_duration_sec,
            "track_watchdog_extra_sec": self.cfg.track_watchdog_extra_sec,
            "user_cooldown_sec": self.cfg.user_cooldown_sec,
            "sr_cost": self._sr_cost,
        }
        effective: dict[str, int] = {}
        for key, default in defaults.items():
            value = stored.get(key)
            if value is None:
                seed[key] = default
                effective[key] = default
            else:
                effective[key] = value
        if seed:
            await queue_db.set_queue_limits(self._db, **seed)
        self._apply_queue_limits(effective)

    def _apply_queue_limits(self, limits: dict[str, int]) -> None:
        if "max_queue_size" in limits:
            self.cfg.max_queue_size = limits["max_queue_size"]
            self.queue.max_size = limits["max_queue_size"]
        if "max_duration_sec" in limits:
            self.cfg.max_duration_sec = limits["max_duration_sec"]
        if "track_watchdog_extra_sec" in limits:
            self.cfg.track_watchdog_extra_sec = limits["track_watchdog_extra_sec"]
        if "user_cooldown_sec" in limits:
            self.cfg.user_cooldown_sec = limits["user_cooldown_sec"]
        if "sr_cost" in limits:
            self._sr_cost = limits["sr_cost"]

    def queue_limits(self) -> dict[str, int]:
        return {
            "max_queue_size": self.cfg.max_queue_size,
            "max_duration_sec": self.cfg.max_duration_sec,
            "track_watchdog_extra_sec": self.cfg.track_watchdog_extra_sec,
            "user_cooldown_sec": self.cfg.user_cooldown_sec,
            "sr_cost": self._sr_cost,
        }

    async def set_queue_limits(
        self,
        *,
        max_queue_size: Optional[int] = None,
        max_duration_sec: Optional[int] = None,
        track_watchdog_extra_sec: Optional[int] = None,
        user_cooldown_sec: Optional[int] = None,
        sr_cost: Optional[int] = None,
    ) -> dict[str, int]:
        updates: dict[str, int] = {}
        if max_queue_size is not None:
            if not isinstance(max_queue_size, int) or max_queue_size < 1:
                raise ValueError("max_queue_size")
            updates["max_queue_size"] = max_queue_size
        if max_duration_sec is not None:
            if not isinstance(max_duration_sec, int) or max_duration_sec < 1:
                raise ValueError("max_duration_sec")
            updates["max_duration_sec"] = max_duration_sec
        if track_watchdog_extra_sec is not None:
            if not isinstance(track_watchdog_extra_sec, int) or track_watchdog_extra_sec < 0:
                raise ValueError("track_watchdog_extra_sec")
            updates["track_watchdog_extra_sec"] = track_watchdog_extra_sec
        if user_cooldown_sec is not None:
            if not isinstance(user_cooldown_sec, int) or user_cooldown_sec < 0:
                raise ValueError("user_cooldown_sec")
            updates["user_cooldown_sec"] = user_cooldown_sec
        if sr_cost is not None:
            if not isinstance(sr_cost, int) or sr_cost < 0:
                raise ValueError("sr_cost")
            updates["sr_cost"] = sr_cost
        if updates:
            await queue_db.set_queue_limits(self._db, **updates)
            self._apply_queue_limits(updates)
            log.info("Лимиты очереди обновлены: %s", updates)
        return self.queue_limits()

    async def close(self) -> None:
        await self.playback.close()
        await self.player.close()
        self.ym_stream.cleanup_all()

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    @property
    def orders_enabled(self) -> bool:
        return self._orders_enabled

    @property
    def block_ym_explicit(self) -> bool:
        return self._block_ym_explicit

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

    async def skip_current(self) -> None:
        """Пропуск текущего трека (аналог !пропуск)."""
        if not self.queue.is_playing:
            raise RuntimeError("nothing_playing")
        await self.player.send_skip(self.queue.current_token)
        if not self.player.has_clients:
            token = self.queue.current_token
            await self.queue.force_skip()
            self.ym_stream.cleanup(token)
            await self.advance(expected_token=None)

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

    async def set_block_ym_explicit(self, enabled: bool) -> None:
        if enabled == self._block_ym_explicit:
            return
        await queue_db.set_block_ym_explicit(self._db, enabled)
        self._block_ym_explicit = enabled
        self.ym_stream.set_block_explicit(enabled)
        log.info("Блокировка YM explicit: %s", "вкл" if enabled else "выкл")

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

        if self.cfg.user_cooldown_sec > 0:
            last = self._cooldowns.get(msg.user_id, 0.0)
            wait = self.cfg.user_cooldown_sec - (time.time() - last)
            if wait > 0:
                await self._say(f"{msg.user_name}, подожди ещё {int(wait) + 1}с перед следующим заказом")
                return

        if self.queue.is_full():
            await self._say(f"{msg.user_name}, очередь заполнена ({self.cfg.max_queue_size})")
            return

        result = validate_order(arg)
        if not result.ok or not result.provider or not result.media_id:
            await self._say(f"{msg.user_name}, {result.reason}")
            return

        if result.provider == PROVIDER_YOUTUBE and not self.playback.youtube_available:
            await self._say(
                f"{msg.user_name}, плеер не может подключиться к YouTube — "
                "заказ YouTube сейчас недоступен (можно Яндекс Музыку)"
            )
            return

        if result.provider == PROVIDER_YANDEX and not self.playback.yandex_configured:
            await self._say(
                f"{msg.user_name}, Яндекс Музыка не настроена "
                "(нужен YANDEX_MUSIC_TOKEN — tools\\yandex_music_token.cmd)"
            )
            return

        if self._sr_cost > 0:
            if self._points is None:
                await self._say(f"{msg.user_name}, заказ песен временно недоступен")
                return
            balance = await self._points.get_balance(msg.user_id)
            if balance < self._sr_cost:
                await self._say(
                    f"{msg.user_name}, недостаточно принцесс: "
                    f"нужно {self._sr_cost}, у тебя {balance} {pluralize_princess(balance)}"
                )
                return
            await self._points.add(msg.user_id, -self._sr_cost)

        track = Track(
            video_id=result.media_id,
            requested_by=msg.user_id,
            requested_by_name=msg.user_name,
            url=result.url,
            title="",
            paid_cost=self._sr_cost if self._sr_cost > 0 else 0,
            provider=result.provider,
            album_id=result.album_id or "",
        )
        position = await self.queue.add(track)
        self._cooldowns[msg.user_id] = time.time()
        if self._sr_cost > 0:
            await self._say(
                f"{msg.user_name}, добавлено в очередь (#{position}), "
                f"списано {self._sr_cost} {pluralize_princess(self._sr_cost)}"
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
        await self.skip_current()
        await self._say(f"{msg.user_name} пропустил трек")

    async def _cmd_queue(self, msg: ChatMessage) -> None:
        upcoming = self.queue.upcoming(3)
        if not upcoming and not self.queue.is_playing:
            await self._say("Очередь пуста")
            return
        parts = [f"в очереди: {len(self.queue)}"]
        if upcoming:
            ids = ", ".join(t.short_label() for t in upcoming)
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
