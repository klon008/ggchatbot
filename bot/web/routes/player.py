"""OBS Browser Source: player.html/js и WebSocket /ws."""
from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Optional

from aiohttp import WSMsgType, web

from bot.web.static import serve_obs_file

log = logging.getLogger("song_request.obs")

StatusHandler = Callable[[dict], Awaitable[None]]


class PlayerRoutes:
    def __init__(self, on_status: StatusHandler) -> None:
        self._on_status = on_status
        self._clients: set[web.WebSocketResponse] = set()

    def register(self, app: web.Application) -> None:
        app.add_routes(
            [
                web.get("/", self._handle_index),
                web.get("/player.html", self._handle_index),
                web.get("/player.js", self._handle_player_js),
                web.get("/ws", self._handle_ws),
            ]
        )

    async def close(self) -> None:
        for ws in list(self._clients):
            await ws.close()

    async def _handle_index(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("player.html", "text/html; charset=utf-8")

    async def _handle_player_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("player.js", "application/javascript; charset=utf-8")

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

    async def send_toggle_pause(self, token: Optional[str]) -> None:
        await self.broadcast({"action": "toggle_pause", "token": token})

    async def send_queue_state(self, snapshot: dict) -> None:
        await self.broadcast({"action": "queue_state", **snapshot})
