"""Оркестратор: связывает чат GoodGame, очередь и плеер в OBS.

Python — единственный источник правды. События завершения принимаются только
с актуальным ``token`` (защита от двойного скипа и запоздавших событий).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from config import Config

from .goodgame_client import ChatMessage, GoodGameClient
from .obs_server import ObsServer
from .queue_manager import QueueManager, Track
from .youtube_validator import canonical_url, validate_request

log = logging.getLogger("app")


class SongRequestBot:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.queue = QueueManager(max_size=cfg.max_queue_size)
        self.obs = ObsServer(cfg.obs_host, cfg.obs_port, on_status=self._on_obs_status)
        self.gg = GoodGameClient(
            login=cfg.gg_login,
            password=cfg.gg_password,
            channel_id=cfg.gg_channel_id,
            on_message=self._on_chat_message,
            user_id=cfg.gg_user_id,
        )
        self._advance_lock = asyncio.Lock()
        self._cooldowns: dict[str, float] = {}
        self._watchdog: Optional[asyncio.Task] = None

    # --- жизненный цикл --------------------------------------------------
    async def run(self) -> None:
        await self.obs.start()
        # На старте была незавершённая очередь? Дадим плееру подключиться,
        # затем воспроизведение стартует по статусу "ready".
        await self.gg.run()  # блокирует до остановки

    async def close(self) -> None:
        if self._watchdog:
            self._watchdog.cancel()
        await self.gg.close()
        await self.obs.stop()

    # --- чат -------------------------------------------------------------
    async def _on_chat_message(self, msg: ChatMessage) -> None:
        text = msg.text.strip()
        if not text.startswith("!"):
            return
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

    async def _cmd_sr(self, msg: ChatMessage, arg: str) -> None:
        # Антиспам по кулдауну.
        if self.cfg.user_cooldown_sec > 0:
            last = self._cooldowns.get(msg.user_id, 0.0)
            wait = self.cfg.user_cooldown_sec - (time.time() - last)
            if wait > 0:
                await self._reply(f"@{msg.user_name}, подожди ещё {int(wait) + 1}с перед следующим заказом")
                return

        if self.queue.is_full():
            await self._reply(f"@{msg.user_name}, очередь заполнена ({self.cfg.max_queue_size})")
            return

        result = validate_request(arg)
        if not result.ok:
            await self._reply(f"@{msg.user_name}, {result.reason}")
            return

        track = Track(
            video_id=result.video_id,
            requested_by=msg.user_id,
            requested_by_name=msg.user_name,
            url=canonical_url(result.video_id),
            title="",
        )
        position = self.queue.add(track)
        self._cooldowns[msg.user_id] = time.time()
        await self._reply(f"@{msg.user_name}, добавлено в очередь (#{position})")

        # Если сейчас ничего не играет — пробуем стартовать сразу.
        if not self.queue.is_playing:
            await self._advance(expected_token=None)

    async def _cmd_skip(self, msg: ChatMessage) -> None:
        if not msg.is_moderator:
            await self._reply(f"@{msg.user_name}, команда !skip доступна только модераторам")
            return
        if not self.queue.is_playing:
            await self._reply("Сейчас ничего не играет")
            return
        await self.obs.send_skip(self.queue.current_token)
        await self._reply(f"@{msg.user_name} пропустил трек")
        # Плеер подтвердит скип статусом ended с текущим token; но на случай,
        # если плеер не подключён — продвигаем очередь принудительно.
        if not self.obs.has_clients:
            self.queue.force_skip()
            await self._advance(expected_token=None)

    async def _cmd_queue(self, msg: ChatMessage) -> None:
        upcoming = self.queue.upcoming(3)
        if not upcoming and not self.queue.is_playing:
            await self._reply("Очередь пуста")
            return
        parts = [f"в очереди: {len(self.queue)}"]
        if upcoming:
            ids = ", ".join(t.video_id for t in upcoming)
            parts.append(f"далее: {ids}")
        await self._reply(" • ".join(parts))

    async def _cmd_song(self, msg: ChatMessage) -> None:
        if self.queue.current:
            cur = self.queue.current
            who = cur.requested_by_name or cur.requested_by
            label = cur.title or cur.url
            await self._reply(f"сейчас играет: {who} — {label}")
        else:
            await self._reply("сейчас ничего не играет")

    async def _send_play(self, track: Track, token: str) -> None:
        await self.obs.send_play(
            track.video_id,
            token,
            self.cfg.max_duration_sec,
            requested_by_name=track.requested_by_name,
            title=track.title,
        )

    # --- OBS -------------------------------------------------------------
    async def _on_obs_status(self, data: dict) -> None:
        status = data.get("status")
        if status == "ready":
            log.info("Плеер готов.")
            # Ресинк: если что-то должно играть — перезапустим текущий,
            # иначе стартуем следующий из очереди.
            if self.queue.is_playing and self.queue.current:
                await self._send_play(self.queue.current, self.queue.current_token or "")
                self._arm_watchdog(self.queue.current_token)
            else:
                await self._advance(expected_token=None)
            return

        token = data.get("token")
        if status in ("ended", "error", "too_long"):
            reason = {
                "error": "видео недоступно для воспроизведения",
                "too_long": "трек слишком длинный или это live-стрим",
            }.get(status)
            await self._advance(expected_token=token, skip_reason=reason)

    # --- продвижение очереди --------------------------------------------
    async def _advance(self, expected_token: Optional[str], skip_reason: Optional[str] = None) -> None:
        """Завершить текущий трек (если токен актуален) и запустить следующий."""
        async with self._advance_lock:
            # Завершаем текущий, только если событие относится к актуальному треку.
            if self.queue.is_playing:
                if expected_token is not None:
                    if not self.queue.finish_current(expected_token):
                        return  # устаревшее событие — игнор
                    if skip_reason:
                        await self._reply(f"Пропуск: {skip_reason}")
                else:
                    # Явное продвижение без токена (force skip / первый старт).
                    if self.queue.current is not None:
                        self.queue.force_skip()

            nxt = self.queue.start_next()
            if nxt is None:
                await self.obs.send_queue_state(self.queue.snapshot())
                log.info("Очередь пуста — ожидание новых заказов.")
                return

            track, token = nxt
            log.info("Воспроизведение: %s (token=%s)", track.video_id, token)
            await self._send_play(track, token)
            self._arm_watchdog(token)

    # --- watchdog: страховка от «зависших» треков -----------------------
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
            await self._advance(expected_token=token, skip_reason="таймаут воспроизведения")

    # --- утилиты ---------------------------------------------------------
    async def _reply(self, text: str) -> None:
        try:
            await self.gg.send_message(text)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось отправить сообщение в чат.")
