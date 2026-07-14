"""Управление воспроизведением очереди и обработка статусов OBS-плеера."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from bot.economy import PointsStore, pluralize_princess
from bot.web.routes.player import PlayerRoutes
from config import Config

from .queue import QueueManager, Track

log = logging.getLogger("song_request")

SayFn = Callable[[str], Awaitable[None]]
PointsGetter = Callable[[], Optional[PointsStore]]

_YT_ERROR_LABELS: dict[int | str, str] = {
    2: "неверный параметр запроса",
    5: "ошибка HTML5-плеера",
    100: "видео удалено или приватное",
    101: "встраивание запрещено владельцем",
    150: "встраивание запрещено владельцем",
    153: "нужен HTTP-URL (не file://) и валидный Referer",
    "youtube_api_unavailable": "YouTube IFrame API недоступен (сеть или блокировка)",
}


class PlaybackController:
    def __init__(
        self,
        cfg: Config,
        queue: QueueManager,
        player: PlayerRoutes,
        points_getter: PointsGetter,
        say: SayFn,
    ) -> None:
        self._cfg = cfg
        self._queue = queue
        self._player = player
        self._points_getter = points_getter
        self._say = say
        self._advance_lock = asyncio.Lock()
        self._watchdog: Optional[asyncio.Task] = None
        self._youtube_api_warned = False
        self.player_paused = False

    async def close(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()

    def cancel_watchdog(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()
            self._watchdog = None

    def arm_watchdog(self, token: Optional[str]) -> None:
        self.cancel_watchdog()
        if token is None:
            return
        timeout = self._cfg.max_duration_sec + self._cfg.track_watchdog_extra_sec
        self._watchdog = asyncio.create_task(self._watchdog_run(token, timeout))

    async def on_obs_status(self, data: dict) -> None:
        status = data.get("status")
        if status == "ready":
            if data.get("overlay") == "booster":
                return
            log.info(
                "Плеер готов (youtubeApi=%s, state=%s).",
                data.get("youtubeApi"),
                data.get("youtubeApiState"),
            )
            if data.get("youtubeApi") is False:
                await self._warn_youtube_api_unavailable(data)
            if self._queue.is_playing and self._queue.current:
                await self._send_play(self._queue.current, self._queue.current_token or "")
                self.arm_watchdog(self._queue.current_token)
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
            self.player_paused = False
            if self._queue.is_playing:
                finished_track = self._queue.current
                if expected_token is not None:
                    if not await self._queue.finish_current(expected_token):
                        return
                    if skip_reason and finished_track is not None:
                        await self._notify_playback_failure(finished_track, skip_reason)
                    elif skip_reason:
                        await self._say(f"Пропуск: {skip_reason}")
                elif self._queue.current is not None:
                    await self._queue.force_skip()

            nxt = await self._queue.start_next()
            if nxt is None:
                await self._player.send_queue_state(self._queue.snapshot())
                log.info("Очередь пуста — ожидание новых заказов.")
                return

            track, token = nxt
            log.info("Воспроизведение: %s (token=%s)", track.video_id, token)
            await self._send_play(track, token)
            self.arm_watchdog(token)

    async def clear_queue_with_refunds(self) -> int:
        async with self._advance_lock:
            self.player_paused = False
            tracks = self._queue.all_tracks()
            self.cancel_watchdog()
            if self._queue.is_playing:
                await self._player.send_skip(self._queue.current_token)
            total_refunded = 0
            for track in tracks:
                refunded = await self._refund_track(track)
                if refunded:
                    name = track.requested_by_name or track.requested_by
                    log.info(
                        "Возврат %d принцесс пользователю %s (%s) при отключении заказов",
                        refunded,
                        track.requested_by,
                        name,
                    )
                    total_refunded += refunded
            await self._queue.clear()
            await self._player.send_queue_state(self._queue.snapshot())
            log.info("Очередь очищена (%d трек(ов)), заказы отключены.", len(tracks))
            return total_refunded

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

    async def _notify_playback_failure(self, track: Track, reason: str) -> None:
        name = track.requested_by_name or track.requested_by
        cost = track.paid_cost
        points = self._points_getter()
        if cost > 0 and points is not None:
            await points.add(track.requested_by, cost)
            await self._say(
                f"@{name}, не удалось воспроизвести: {reason}. "
                f"Возвращено {cost} {pluralize_princess(cost)}"
            )
        else:
            await self._say(f"@{name}, не удалось воспроизвести: {reason}")

    async def _refund_track(self, track: Track) -> int:
        cost = track.paid_cost
        points = self._points_getter()
        if cost > 0 and points is not None:
            await points.add(track.requested_by, cost)
            return cost
        return 0

    async def _send_play(self, track: Track, token: str) -> None:
        await self._player.send_play(
            track.video_id,
            token,
            self._cfg.max_duration_sec,
            requested_by_name=track.requested_by_name,
            title=track.title,
        )

    async def _watchdog_run(self, token: str, timeout: int) -> None:
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return
        if self._queue.current_token == token:
            log.warning(
                "Watchdog: трек token=%s не завершился за %dс — принудительный переход.",
                token,
                timeout,
            )
            await self.advance(expected_token=token, skip_reason="таймаут воспроизведения")
