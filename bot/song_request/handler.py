"""Song-request: очередь YouTube, OBS-плеер, команды !sr / !skip."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.goodgame import ChatMessage
from bot.princess.economy import pluralize_princess
from bot.princess.storage import PointsStore
from config import Config

from .obs_server import ObsServer
from .queue import QueueManager, Track
from .settings import SR_COST
from .youtube import canonical_url, validate_request

log = logging.getLogger("song_request")

ReplyFn = Callable[[str], Awaitable[None]]

_YT_ERROR_LABELS: dict[int | str, str] = {
    2: "неверный параметр запроса",
    5: "ошибка HTML5-плеера",
    100: "видео удалено или приватное",
    101: "встраивание запрещено владельцем",
    150: "встраивание запрещено владельцем",
    153: "нужен HTTP-URL (не file://) и валидный Referer",
    "youtube_api_unavailable": "YouTube IFrame API недоступен (сеть или блокировка)",
}


class SongRequestHandler:
    def __init__(self, cfg: Config, db: Database) -> None:
        self.cfg = cfg
        self._db = db
        self.queue = QueueManager(db, max_size=cfg.max_queue_size)
        self.obs = ObsServer(
            cfg.obs_host,
            cfg.obs_port,
            on_status=self._on_obs_status,
            db=db,
            queue=self.queue,
        )
        self._advance_lock = asyncio.Lock()
        self._cooldowns: dict[str, float] = {}
        self._watchdog: Optional[asyncio.Task] = None
        self._reply: Optional[ReplyFn] = None
        self._points: Optional[PointsStore] = None
        self._youtube_api_warned = False

    async def start(self) -> None:
        await self.queue.load()
        await self.obs.start()
        log.info("Song-request модуль запущен.")

    async def close(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()
        await self.obs.stop()

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    async def handle_message(self, msg: ChatMessage) -> bool:
        text = msg.text.strip()
        if not text.startswith("!"):
            return False

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "!sr":
            await self._cmd_sr(msg, arg)
        elif cmd == "!skip":
            await self._cmd_skip(msg)
        elif cmd in ("!queue", "!q"):
            await self._cmd_queue(msg)
        elif cmd in ("!song", "!now"):
            await self._cmd_song(msg)
        else:
            return False

        return True

    async def _cmd_sr(self, msg: ChatMessage, arg: str) -> None:
        if self.cfg.user_cooldown_sec > 0:
            last = self._cooldowns.get(msg.user_id, 0.0)
            wait = self.cfg.user_cooldown_sec - (time.time() - last)
            if wait > 0:
                await self._say(f"@{msg.user_name}, подожди ещё {int(wait) + 1}с перед следующим заказом")
                return

        if self.queue.is_full():
            await self._say(f"@{msg.user_name}, очередь заполнена ({self.cfg.max_queue_size})")
            return

        result = validate_request(arg)
        if not result.ok:
            await self._say(f"@{msg.user_name}, {result.reason}")
            return

        if SR_COST > 0:
            if self._points is None:
                await self._say(f"@{msg.user_name}, заказ песен временно недоступен")
                return
            balance = await self._points.get_balance(msg.user_id)
            if balance < SR_COST:
                await self._say(
                    f"@{msg.user_name}, недостаточно принцесс: "
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
                f"@{msg.user_name}, добавлено в очередь (#{position}), "
                f"списано {SR_COST} {pluralize_princess(SR_COST)}"
            )
        else:
            await self._say(f"@{msg.user_name}, добавлено в очередь (#{position})")

        if not self.queue.is_playing:
            await self.advance(expected_token=None)

    async def _cmd_skip(self, msg: ChatMessage) -> None:
        if not msg.is_moderator:
            await self._say(f"@{msg.user_name}, команда !skip доступна только модераторам")
            return
        if not self.queue.is_playing:
            await self._say("Сейчас ничего не играет")
            return
        await self.obs.send_skip(self.queue.current_token)
        await self._say(f"@{msg.user_name} пропустил трек")
        if not self.obs.has_clients:
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

    def _format_player_error(self, data: dict) -> str:
        message = (data.get("message") or "").strip()
        if message:
            return message
        code = data.get("code")
        if code is not None:
            label = _YT_ERROR_LABELS.get(code)
            if label:
                return label
            return f"ошибка плеера (код {code})"
        return "видео недоступно для воспроизведения"

    async def _warn_youtube_api_unavailable(self, data: dict) -> None:
        err = (data.get("youtubeApiError") or data.get("message") or "").strip()
        if not err:
            err = "не удалось загрузить YouTube IFrame API"
        log.warning("YouTube API недоступен в OBS-плеере: %s", err)
        if self._youtube_api_warned:
            return
        self._youtube_api_warned = True
        await self._say(
            "Плеер OBS не может подключиться к YouTube (Проблемы с сетью). "
        )

    async def _on_obs_status(self, data: dict) -> None:
        status = data.get("status")
        if status == "ready":
            log.info(
                "Плеер готов (youtubeApi=%s, state=%s).",
                data.get("youtubeApi"),
                data.get("youtubeApiState"),
            )
            if data.get("youtubeApi") is False:
                await self._warn_youtube_api_unavailable(data)
            if self.queue.is_playing and self.queue.current:
                await self._send_play(self.queue.current, self.queue.current_token or "")
                self._arm_watchdog(self.queue.current_token)
            else:
                await self.advance(expected_token=None)
            return

        if status == "api_error":
            await self._warn_youtube_api_unavailable(data)
            return

        token = data.get("token")
        if status == "ended":
            log.info("Трек завершён: videoId=%s token=%s", data.get("videoId"), token)
            await self.advance(expected_token=token)
            return

        if status == "error":
            reason = self._format_player_error(data)
            log.warning(
                "Ошибка плеера: videoId=%s token=%s code=%s — %s",
                data.get("videoId"),
                token,
                data.get("code"),
                reason,
            )
            await self.advance(expected_token=token, skip_reason=reason)
            return

        if status == "too_long":
            reason = (data.get("message") or "").strip() or "трек слишком длинный или это live-стрим"
            log.warning(
                "Трек отклонён по длительности: videoId=%s token=%s — %s",
                data.get("videoId"),
                token,
                reason,
            )
            await self.advance(expected_token=token, skip_reason=reason)

    async def advance(self, expected_token: Optional[str], skip_reason: Optional[str] = None) -> None:
        async with self._advance_lock:
            if self.queue.is_playing:
                finished_track = self.queue.current
                if expected_token is not None:
                    if not await self.queue.finish_current(expected_token):
                        return
                    if skip_reason:
                        await self._say(f"Пропуск: {skip_reason}")
                        if finished_track is not None:
                            await self._refund_track(finished_track, skip_reason)
                elif self.queue.current is not None:
                    await self.queue.force_skip()

            nxt = await self.queue.start_next()
            if nxt is None:
                await self.obs.send_queue_state(self.queue.snapshot())
                log.info("Очередь пуста — ожидание новых заказов.")
                return

            track, token = nxt
            log.info("Воспроизведение: %s (token=%s)", track.video_id, token)
            await self._send_play(track, token)
            self._arm_watchdog(token)

    async def _refund_track(self, track: Track, reason: str) -> None:
        cost = track.paid_cost
        if cost <= 0 or self._points is None:
            return
        await self._points.add(track.requested_by, cost)
        name = track.requested_by_name or track.requested_by
        await self._say(
            f"@{name}, возвращено {cost} {pluralize_princess(cost)} — {reason}"
        )

    async def _send_play(self, track: Track, token: str) -> None:
        await self.obs.send_play(
            track.video_id,
            token,
            self.cfg.max_duration_sec,
            requested_by_name=track.requested_by_name,
            title=track.title,
        )

    def _arm_watchdog(self, token: Optional[str]) -> None:
        if self._watchdog:
            self._watchdog.cancel()
        if token is None:
            return
        timeout = self.cfg.max_duration_sec + self.cfg.track_watchdog_extra_sec
        self._watchdog = asyncio.create_task(self._watchdog_run(token, timeout))

    async def _watchdog_run(self, token: str, timeout: int) -> None:
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return
        if self.queue.current_token == token:
            log.warning("Watchdog: трек token=%s не завершился за %dс — принудительный переход.", token, timeout)
            await self.advance(expected_token=token, skip_reason="таймаут воспроизведения")

    async def _say(self, text: str) -> None:
        if self._reply:
            await self._reply(text)
