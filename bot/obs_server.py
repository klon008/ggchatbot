"""Локальный сервер для OBS Browser Source.

aiohttp на одном порту:
  * ``GET /``, ``/player.html``, ``/player.js`` — статика из obs/ (нужен валидный
    origin/referer, иначе YouTube отдаёт error 153 при open как top-level).
  * ``GET /ws`` — WebSocket для двусторонней связи с плеером.

Python шлёт плееру ``play``/``skip``/``queue_state``; плеер рапортует
``ready``/``ended``/``error``/``too_long`` с тем же ``token``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

from aiohttp import WSMsgType, web

log = logging.getLogger("obs")

OBS_DIR = Path(__file__).resolve().parent.parent / "obs"

# Тип колбэка обработки входящего статуса от плеера.
StatusHandler = Callable[[dict], Awaitable[None]]


class ObsServer:
    def __init__(self, host: str, port: int, on_status: StatusHandler) -> None:
        self.host = host
        self.port = port
        self._on_status = on_status
        self._clients: set[web.WebSocketResponse] = set()
        self._runner: Optional[web.AppRunner] = None
        self._app = web.Application()
        self._app.add_routes(
            [
                web.get("/", self._handle_index),
                web.get("/player.html", self._handle_index),
                web.get("/player.js", self._handle_player_js),
                web.get("/ws", self._handle_ws),
            ]
        )

    # --- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        log.info("OBS-сервер запущен: http://%s:%d/player.html", self.host, self.port)

    async def stop(self) -> None:
        for ws in list(self._clients):
            await ws.close()
        if self._runner:
            await self._runner.cleanup()

    # --- HTTP статика ----------------------------------------------------
    async def _handle_index(self, request: web.Request) -> web.StreamResponse:
        return await self._serve_file("player.html", "text/html; charset=utf-8")

    async def _handle_player_js(self, request: web.Request) -> web.StreamResponse:
        return await self._serve_file("player.js", "application/javascript; charset=utf-8")

    async def _serve_file(self, name: str, content_type: str) -> web.StreamResponse:
        path = OBS_DIR / name
        if not path.exists():
            return web.Response(status=404, text=f"{name} not found")
        return web.Response(body=path.read_bytes(), content_type=content_type.split(";")[0],
                            charset="utf-8")

    # --- WebSocket -------------------------------------------------------
    @property
    def has_clients(self) -> bool:
        return len(self._clients) > 0

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._clients.add(ws)
        log.info("Плеер подключился (клиентов: %d)", len(self._clients))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._dispatch(msg.data)
                elif msg.type == WSMsgType.ERROR:
                    log.warning("WS ошибка: %s", ws.exception())
        finally:
            self._clients.discard(ws)
            log.info("Плеер отключился (клиентов: %d)", len(self._clients))
        return ws

    async def _dispatch(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Некорректный JSON от плеера: %s", raw[:200])
            return
        if not isinstance(data, dict):
            return
        await self._on_status(data)

    # --- отправка команд плееру -----------------------------------------
    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            log.debug("Нет подключённых плееров, команда %s пропущена", payload.get("action"))
            return
        msg = json.dumps(payload, ensure_ascii=False)
        dead: list[web.WebSocketResponse] = []
        for ws in self._clients:
            try:
                await ws.send_str(msg)
            except ConnectionError:
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    async def send_play(
        self,
        video_id: str,
        token: str,
        max_duration_sec: int,
        requested_by_name: str = "",
        title: str = "",
    ) -> None:
        await self.broadcast(
            {
                "action": "play",
                "videoId": video_id,
                "token": token,
                "maxDurationSec": max_duration_sec,
                "requestedBy": requested_by_name,
                "title": title,
            }
        )

    async def send_skip(self, token: Optional[str]) -> None:
        await self.broadcast({"action": "skip", "token": token})

    async def send_queue_state(self, snapshot: dict) -> None:
        await self.broadcast({"action": "queue_state", **snapshot})
