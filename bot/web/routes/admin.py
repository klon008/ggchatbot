"""Маршруты админ-панели (points CRUD, queue delete) для локального HTTP-сервера."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from aiohttp import web

from bot.db import Database
from bot.db import points as points_db
from bot.db import users as users_db
from bot.web.api import (
    error_response,
    json_response,
    parse_balance,
    parse_user_id,
    parse_user_name,
    read_json,
)
from bot.web.static import serve_obs_file

if TYPE_CHECKING:
    from bot.economy.points import PointsStore
    from bot.song_request.handler import SongRequestHandler
    from bot.song_request.queue import QueueManager

log = logging.getLogger("admin")

ViewersFetchFn = Callable[[], Awaitable[list[dict]]]


class AdminRoutes:
    def __init__(
        self,
        db: Database,
        queue: "QueueManager",
        sr_handler: "SongRequestHandler",
    ) -> None:
        self._db = db
        self._queue = queue
        self._sr = sr_handler
        self._fetch_viewers: Optional[ViewersFetchFn] = None
        self._points: Optional["PointsStore"] = None

    def bind_user_names(
        self,
        fetch_viewers: ViewersFetchFn,
        points: "PointsStore",
    ) -> None:
        self._fetch_viewers = fetch_viewers
        self._points = points

    def _require_points(self) -> "PointsStore":
        if self._points is None:
            raise RuntimeError("PointsStore not bound")
        return self._points

    def register(self, app: web.Application) -> None:
        app.add_routes(
            [
                web.get("/admin.html", self._handle_index),
                web.get("/admin.js", self._handle_admin_js),
                web.get("/api/points", self._api_points_list),
                web.get("/api/points/{user_id}", self._api_points_get),
                web.post("/api/points", self._api_points_create),
                web.put("/api/points/{user_id}", self._api_points_update),
                web.delete("/api/points/{user_id}", self._api_points_delete),
                web.get("/api/queue", self._api_queue_get),
                web.post("/api/queue/toggle-pause", self._api_queue_toggle_pause),
                web.delete("/api/queue/waiting/{index}", self._api_queue_delete),
                web.get("/api/song-request", self._api_sr_get),
                web.put("/api/song-request", self._api_sr_put),
                web.post("/api/user-names/sync", self._api_user_names_sync),
            ]
        )

    async def _handle_index(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("admin.html", "text/html; charset=utf-8")

    async def _handle_admin_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("admin.js", "application/javascript; charset=utf-8")

    async def _api_points_list(self, request: web.Request) -> web.Response:
        try:
            points = self._require_points()
        except RuntimeError:
            return error_response("PointsStore недоступен", status=503)
        items = await points.list_entries()
        return json_response({"items": items})

    async def _api_points_get(self, request: web.Request) -> web.Response:
        try:
            points = self._require_points()
        except RuntimeError:
            return error_response("PointsStore недоступен", status=503)
        user_id = request.match_info["user_id"]
        entry = await points.get_user_entry(user_id)
        if entry is None:
            return error_response("Пользователь не найден", status=404)
        return json_response(entry)

    async def _api_points_create(self, request: web.Request) -> web.Response:
        try:
            points = self._require_points()
        except RuntimeError:
            return error_response("PointsStore недоступен", status=503)
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        user_id = parse_user_id(data.get("user_id"))
        balance = parse_balance(data.get("balance", 0))
        user_name = parse_user_name(data.get("user_name"))
        if user_id is None:
            return error_response("user_id обязателен")
        if balance is None:
            return error_response("balance должен быть целым числом >= 0")
        existing = await points.get_user_entry(user_id)
        if existing is not None:
            return error_response("Пользователь уже существует", status=409)
        await points.set_balance(user_id, balance)
        if user_name:
            await users_db.touch_user_name(self._db, user_id, user_name)
            points.mark_known(user_id)
        entry = await points.get_user_entry(user_id)
        assert entry is not None
        return json_response(entry, status=201)

    async def _api_points_update(self, request: web.Request) -> web.Response:
        try:
            points = self._require_points()
        except RuntimeError:
            return error_response("PointsStore недоступен", status=503)
        user_id = request.match_info["user_id"]
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        balance = parse_balance(data.get("balance"))
        if balance is None:
            return error_response("balance должен быть целым числом >= 0")
        existing = await points.get_user_entry(user_id)
        if existing is None:
            return error_response("Пользователь не найден", status=404)
        await points.set_balance(user_id, balance)
        entry = await points.get_user_entry(user_id)
        assert entry is not None
        return json_response(entry)

    async def _api_points_delete(self, request: web.Request) -> web.Response:
        try:
            points = self._require_points()
        except RuntimeError:
            return error_response("PointsStore недоступен", status=503)
        user_id = request.match_info["user_id"]
        existing = await points.get_user_entry(user_id)
        if existing is None:
            return error_response("Пользователь не найден", status=404)
        points.clear_pending(user_id)
        deleted = await points_db.delete_user(self._db, user_id)
        if not deleted:
            return error_response("Пользователь не найден", status=404)
        return json_response({"deleted": True, "user_id": user_id})

    async def _api_queue_get(self, request: web.Request) -> web.Response:
        playing = asdict(self._queue.current) if self._queue.current else None
        waiting = self._queue.list_waiting()
        return json_response({
            "playing": playing,
            "waiting": waiting,
            "paused": self._sr.player_paused,
        })

    async def _api_queue_toggle_pause(self, request: web.Request) -> web.Response:
        try:
            paused = await self._sr.toggle_pause()
        except RuntimeError as exc:
            if str(exc) == "nothing_playing":
                return error_response("Сейчас ничего не играет", status=409)
            raise
        return json_response({"paused": paused})

    async def _api_queue_delete(self, request: web.Request) -> web.Response:
        try:
            index = int(request.match_info["index"])
        except ValueError:
            return error_response("index должен быть целым числом")
        removed = await self._queue.remove_waiting(index)
        if not removed:
            return error_response("Трек не найден", status=404)
        return json_response({"deleted": True, "index": index})

    async def _api_sr_get(self, request: web.Request) -> web.Response:
        return json_response({"orders_enabled": self._sr.orders_enabled})

    async def _api_sr_put(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        raw = data.get("orders_enabled")
        if not isinstance(raw, bool):
            return error_response("orders_enabled должен быть true или false")
        await self._sr.set_orders_enabled(raw)
        return json_response({"orders_enabled": self._sr.orders_enabled})

    async def _api_user_names_sync(self, request: web.Request) -> web.Response:
        if self._fetch_viewers is None or self._points is None:
            return error_response("Синхронизация ников недоступна", status=503)
        try:
            users = await self._fetch_viewers()
        except ConnectionError:
            return error_response("Бот не подключён к чату GoodGame", status=503)
        except RuntimeError as exc:
            return error_response(str(exc), status=409)
        except asyncio.TimeoutError:
            return error_response("Таймаут запроса списка зрителей", status=504)

        updated, total = await self._points.sync_online_names(users)
        log.info("Синхронизация ников из админки: %d из %d онлайн", updated, total)
        return json_response({"updated": updated, "total_online": total})
