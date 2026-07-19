"""OBS Browser Source: player, booster, fishing-record, races и WebSocket /ws."""
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
        self._extra_handlers: list[StatusHandler] = []
        self._clients: set[web.WebSocketResponse] = set()
        self._booster_clients: set[web.WebSocketResponse] = set()
        self._fishing_record_clients: set[web.WebSocketResponse] = set()
        self._races_clients: set[web.WebSocketResponse] = set()

    def add_status_handler(self, handler: StatusHandler) -> None:
        self._extra_handlers.append(handler)

    def register(self, app: web.Application) -> None:
        app.add_routes(
            [
                web.get("/", self._handle_index),
                web.get("/player.html", self._handle_index),
                web.get("/player.js", self._handle_player_js),
                web.get("/booster.html", self._handle_booster_html),
                web.get("/booster.js", self._handle_booster_js),
                web.get("/fishing-record.html", self._handle_fishing_record_html),
                web.get("/fishing-record.js", self._handle_fishing_record_js),
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

    async def _handle_booster_html(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("booster.html", "text/html; charset=utf-8")

    async def _handle_booster_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("booster.js", "application/javascript; charset=utf-8")

    async def _handle_fishing_record_html(
        self, request: web.Request
    ) -> web.StreamResponse:
        return await serve_obs_file("fishing-record.html", "text/html; charset=utf-8")

    async def _handle_fishing_record_js(
        self, request: web.Request
    ) -> web.StreamResponse:
        return await serve_obs_file(
            "fishing-record.js", "application/javascript; charset=utf-8"
        )

    @property
    def has_clients(self) -> bool:
        return len(self._clients) > 0

    @property
    def has_booster_clients(self) -> bool:
        return len(self._booster_clients) > 0

    @property
    def has_fishing_record_clients(self) -> bool:
        return len(self._fishing_record_clients) > 0

    @property
    def has_races_clients(self) -> bool:
        return len(self._races_clients) > 0

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        self._clients.add(ws)
        log.info("Плеер подключился (клиентов: %d)", len(self._clients))
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._dispatch(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    log.warning("WS ошибка: %s", ws.exception())
        finally:
            self._clients.discard(ws)
            self._booster_clients.discard(ws)
            self._fishing_record_clients.discard(ws)
            self._races_clients.discard(ws)
            log.info("Плеер отключился (клиентов: %d)", len(self._clients))
        return ws

    async def _dispatch(self, ws: web.WebSocketResponse, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Некорректный JSON от плеера: %s", raw[:200])
            return
        if not isinstance(data, dict):
            return
        if data.get("status") == "ready":
            overlay = data.get("overlay")
            if overlay == "booster":
                self._booster_clients.add(ws)
            elif overlay == "fishing_record":
                self._fishing_record_clients.add(ws)
            elif overlay == "races":
                await self._claim_races_slot(ws)
        await self._on_status(data)
        for handler in self._extra_handlers:
            await handler(data)

    async def _claim_races_slot(self, ws: web.WebSocketResponse) -> None:
        """Один races.html: новый коннект вытесняет старый (без дублей анимации)."""
        for old in list(self._races_clients):
            if old is ws:
                continue
            self._races_clients.discard(old)
            try:
                await old.close(code=4000, message=b"races replaced")
            except Exception:  # noqa: BLE001
                pass
            log.info("Races OBS: предыдущий клиент отключён (слот занят новым)")
        self._races_clients.add(ws)
        log.info("Races OBS подключён")

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

    async def broadcast_fishing_record(self, payload: dict) -> None:
        """Только клиентам fishing-record overlay (не шумим в плеер/бустер)."""
        if not self._fishing_record_clients:
            log.debug("Нет fishing-record overlay, событие пропущено")
            return
        msg = json.dumps(payload, ensure_ascii=False)
        dead: list[web.WebSocketResponse] = []
        for ws in list(self._fishing_record_clients):
            try:
                await ws.send_str(msg)
            except ConnectionError:
                dead.append(ws)
        for ws in dead:
            self._fishing_record_clients.discard(ws)
            self._clients.discard(ws)

    async def broadcast_races(self, payload: dict) -> None:
        """Только races overlay (один слот)."""
        if not self._races_clients:
            log.debug("Нет races overlay, событие %s пропущено", payload.get("action"))
            return
        msg = json.dumps(payload, ensure_ascii=False)
        dead: list[web.WebSocketResponse] = []
        for ws in list(self._races_clients):
            try:
                await ws.send_str(msg)
            except ConnectionError:
                dead.append(ws)
        for ws in dead:
            self._races_clients.discard(ws)
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
