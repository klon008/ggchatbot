"""Управление воспроизведением очереди и обработка статусов OBS-плеера."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Literal, Optional

from bot.economy import PointsStore, pluralize_princess
from bot.web.routes.player import PlayerRoutes
from config import Config

from .queue import PROVIDER_YANDEX, PROVIDER_YOUTUBE, QueueManager, Track
from .yandex_stream import YandexStreamError, YandexStreamService

log = logging.getLogger("song_request")

SayFn = Callable[[str], Awaitable[None]]
PointsGetter = Callable[[], Optional[PointsStore]]
Backend = Literal["youtube", "yandex"]

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
        ym_stream: Optional[YandexStreamService] = None,
    ) -> None:
        self._cfg = cfg
        self._queue = queue
        self._player = player
        self._points_getter = points_getter
        self._say = say
        self._ym = ym_stream
        self._advance_lock = asyncio.Lock()
        self._watchdog: Optional[asyncio.Task] = None
        self._youtube_api_warned = False
        self._youtube_available = True
        self.active_backend: Optional[Backend] = None
        self.player_paused = False

    @property
    def yandex_configured(self) -> bool:
        return self._ym is not None and self._ym.configured

    def _cleanup_ym(self, play_token: Optional[str]) -> None:
        if self._ym is not None:
            self._ym.cleanup(play_token)

    @property
    def youtube_available(self) -> bool:
        return self._youtube_available

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

    @staticmethod
    def _is_youtube_unavailable_error(data: dict) -> bool:
        code = data.get("code")
        if code == "youtube_api_unavailable":
            return True
        message = str(data.get("message") or "").lower()
        return "youtube iframe api" in message or "youtube.com/iframe_api" in message

    async def on_obs_status(self, data: dict) -> None:
        status = data.get("status")
        if status == "ready":
            # booster / races / fishing-record шлют свой ready на тот же /ws
            if data.get("overlay"):
                return
            api_ok = data.get("youtubeApi") is True
            api_state = str(data.get("youtubeApiState") or "")
            log.info(
                "Плеер готов (youtubeApi=%s, state=%s).",
                data.get("youtubeApi"),
                api_state or data.get("youtubeApiState"),
            )
            # idle/loading — API ещё не грузили (lazy-init), это не авария.
            if not api_ok and api_state == "failed":
                await self._handle_youtube_outage(data)
                return

            if api_ok:
                was_down = not self._youtube_available
                self._youtube_available = True
                if was_down:
                    self._youtube_api_warned = False
                    log.info("YouTube IFrame API снова доступен — возобновляем YouTube-очередь.")
            elif api_state in ("idle", "loading") and not self._youtube_available:
                # OBS перезагрузил источник — даём снова принимать заказы YouTube.
                self._youtube_available = True
                self._youtube_api_warned = False
                log.info("Плеер переподключился (state=%s) — снимаем блок YouTube.", api_state)

            if self._queue.is_playing and self._queue.current:
                err = await self._send_play(
                    self._queue.current, self._queue.current_token or ""
                )
                if err:
                    await self.advance(
                        expected_token=self._queue.current_token,
                        skip_reason=err,
                    )
                else:
                    self.arm_watchdog(self._queue.current_token)
            else:
                await self.advance(expected_token=None)
            return

        if status == "api_error":
            await self._handle_youtube_outage(data)
            return

        token = data.get("token")
        if status == "ended":
            log.info(
                "Трек завершён: provider=%s id=%s token=%s",
                data.get("provider"),
                data.get("videoId") or data.get("trackId"),
                token,
            )
            await self.advance(expected_token=token)
            return

        if status == "error":
            reason = self._format_player_error(data)
            log.warning(
                "Ошибка плеера: provider=%s id=%s token=%s code=%s — %s",
                data.get("provider"),
                data.get("videoId") or data.get("trackId"),
                token,
                data.get("code"),
                reason,
            )
            if self._is_youtube_unavailable_error(data):
                await self._handle_youtube_outage(data)
                return
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

    async def _handle_youtube_outage(self, data: dict) -> None:
        """YouTube недоступен: рефанд только YouTube-треков, ЯМузыка продолжает."""
        self._youtube_available = False
        await self._warn_youtube_api_unavailable(data)

        async with self._advance_lock:
            self.player_paused = False
            refunded_tracks: list[Track] = []

            current = self._queue.current
            if current is not None and current.provider == PROVIDER_YOUTUBE:
                self.cancel_watchdog()
                await self._player.send_skip(self._queue.current_token)
                refunded_tracks.append(current)
                await self._queue.force_skip()
                if self.active_backend == PROVIDER_YOUTUBE:
                    self.active_backend = None

            waiting_yt = await self._queue.take_waiting_by_provider(PROVIDER_YOUTUBE)
            refunded_tracks.extend(waiting_yt)

            total_refunded = 0
            for track in refunded_tracks:
                total_refunded += await self._refund_track(track)

            points = self._points_getter()
            if points is not None and total_refunded > 0:
                await points.flush_pending()

            count = len(refunded_tracks)
            if count > 0:
                if total_refunded > 0:
                    await self._say(
                        f"YouTube недоступен — снято YouTube-треков: {count}, "
                        f"возвращено {total_refunded} {pluralize_princess(total_refunded)}. "
                        "Заказы Яндекс Музыки работают."
                    )
                else:
                    await self._say(
                        f"YouTube недоступен — снято YouTube-треков: {count}. "
                        "Заказы Яндекс Музыки работают."
                    )
            else:
                log.info("YouTube недоступен, в очереди не было YouTube-треков.")

            # Продолжить очередь (ЯМузыка), если сейчас ничего не играет.
            if not self._queue.is_playing:
                # advance без повторного захвата lock — вызываем внутреннюю часть
                pass

        if not self._queue.is_playing:
            await self.advance(expected_token=None)

    async def advance(
        self,
        expected_token: Optional[str],
        skip_reason: Optional[str] = None,
        *,
        continue_queue: bool = True,
    ) -> None:
        async with self._advance_lock:
            self.player_paused = False
            if self._queue.is_playing:
                finished_track = self._queue.current
                finished_token = self._queue.current_token
                if expected_token is not None:
                    if not await self._queue.finish_current(expected_token):
                        return
                    if skip_reason and finished_track is not None:
                        await self._notify_playback_failure(finished_track, skip_reason)
                    elif skip_reason:
                        await self._say(f"Пропуск: {skip_reason}")
                    self._cleanup_ym(expected_token)
                elif self._queue.current is not None:
                    await self._queue.force_skip()
                    self._cleanup_ym(finished_token)
                self.active_backend = None

            if not continue_queue:
                await self._player.send_queue_state(self._queue.snapshot())
                log.warning(
                    "Очередь на паузе, в ожидании: %d.",
                    len(self._queue),
                )
                return

            while True:
                nxt = await self._queue.start_next()
                if nxt is None:
                    await self._player.send_queue_state(self._queue.snapshot())
                    self.active_backend = None
                    log.info("Очередь пуста — ожидание новых заказов.")
                    return

                track, token = nxt
                if track.provider == PROVIDER_YOUTUBE and not self._youtube_available:
                    await self._notify_playback_failure(
                        track,
                        "YouTube недоступен",
                    )
                    await self._queue.force_skip()
                    continue

                if track.provider == PROVIDER_YANDEX and not self.yandex_configured:
                    await self._notify_playback_failure(
                        track,
                        "Яндекс Музыка не настроена",
                    )
                    await self._queue.force_skip()
                    continue

                log.info(
                    "Воспроизведение: provider=%s id=%s (token=%s)",
                    track.provider,
                    track.video_id,
                    token,
                )
                err = await self._send_play(track, token)
                if err:
                    await self._notify_playback_failure(track, err)
                    self._cleanup_ym(token)
                    await self._queue.force_skip()
                    continue

                self.arm_watchdog(token)
                return

    async def clear_queue_with_refunds(self, *, reason: str = "отключение заказов") -> int:
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
                        "Возврат %d принцесс пользователю %s (%s) — %s",
                        refunded,
                        track.requested_by,
                        name,
                        reason,
                    )
                    total_refunded += refunded
            await self._queue.clear()
            self.active_backend = None
            if self._ym is not None:
                self._ym.cleanup_all()
            await self._player.send_queue_state(self._queue.snapshot())
            points = self._points_getter()
            if points is not None and total_refunded > 0:
                await points.flush_pending()
            log.info(
                "Очередь очищена (%d трек(ов)), причина: %s, возвращено %d.",
                len(tracks),
                reason,
                total_refunded,
            )
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
            "Заказы Яндекс Музыки по-прежнему доступны."
        )

    async def _notify_playback_failure(self, track: Track, reason: str) -> None:
        name = track.requested_by_name or track.requested_by
        cost = track.paid_cost
        points = self._points_getter()
        if cost > 0 and points is not None:
            await points.add(track.requested_by, cost)
            await self._say(
                f"{name}, не удалось воспроизвести: {reason}. "
                f"Возвращено {cost} {pluralize_princess(cost)}"
            )
        else:
            await self._say(f"{name}, не удалось воспроизвести: {reason}")

    async def _refund_track(self, track: Track) -> int:
        cost = track.paid_cost
        points = self._points_getter()
        if cost > 0 and points is not None:
            await points.add(track.requested_by, cost)
            return cost
        return 0

    async def _send_play(self, track: Track, token: str) -> Optional[str]:
        """Старт трека. Возвращает текст ошибки или None при успехе."""
        provider = track.provider if track.provider in (PROVIDER_YOUTUBE, PROVIDER_YANDEX) else PROVIDER_YOUTUBE
        self.active_backend = provider  # type: ignore[assignment]

        if provider == PROVIDER_YANDEX:
            if self._ym is None or not self._ym.configured:
                return "Яндекс Музыка не настроена"
            try:
                cached = await self._ym.resolve_and_cache(
                    track.video_id,
                    track.album_id or None,
                    token,
                    known_title=track.title,
                )
            except YandexStreamError as exc:
                log.warning("YM resolve failed: %s", exc)
                return str(exc) or "не удалось скачать трек"
            except Exception as exc:  # noqa: BLE001
                log.exception("YM resolve unexpected error")
                return f"ошибка Яндекс Музыки: {exc}"

            if (
                cached.duration_sec > 0
                and self._cfg.max_duration_sec > 0
                and cached.duration_sec > self._cfg.max_duration_sec
            ):
                return (
                    f"трек длиннее лимита ({int(cached.duration_sec)}с)"
                )

            if cached.title and not track.title:
                track.title = cached.title

            await self._player.send_play(
                provider=PROVIDER_YANDEX,
                token=token,
                max_duration_sec=self._cfg.max_duration_sec,
                requested_by_name=track.requested_by_name,
                title=track.title or cached.title,
                video_id=None,
                track_id=track.video_id,
                album_id=track.album_id or "",
                audio_url=cached.audio_url,
                cover_url=cached.cover_url or None,
            )
            return None

        await self._player.send_play(
            provider=PROVIDER_YOUTUBE,
            token=token,
            max_duration_sec=self._cfg.max_duration_sec,
            requested_by_name=track.requested_by_name,
            title=track.title,
            video_id=track.video_id,
            track_id=None,
            album_id="",
            audio_url=None,
            cover_url=None,
        )
        return None

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
