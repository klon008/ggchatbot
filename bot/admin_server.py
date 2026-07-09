"""Маршруты админ-панели (points CRUD, queue delete) для общего OBS HTTP-сервера."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

from bot.db import Database
from bot.db import points as points_db

if TYPE_CHECKING:
    from bot.song_request.handler import SongRequestHandler
    from bot.song_request.queue import QueueManager

log = logging.getLogger("admin")

OBS_DIR = Path(__file__).resolve().parent.parent / "obs"


class AdminServer:
    def __init__(
        self,
        db: Database,
        queue: "QueueManager",
        sr_handler: "SongRequestHandler",
    ) -> None:
        self._db = db
        self._queue = queue
        self._sr = sr_handler

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
                web.delete("/api/queue/waiting/{index}", self._api_queue_delete),
                web.get("/api/song-request", self._api_sr_get),
                web.put("/api/song-request", self._api_sr_put),
            ]
        )

    async def _handle_index(self, request: web.Request) -> web.StreamResponse:
        return await self._serve_file("admin.html", "text/html; charset=utf-8")

    async def _handle_admin_js(self, request: web.Request) -> web.StreamResponse:
        return await self._serve_file("admin.js", "application/javascript; charset=utf-8")

    async def _serve_file(self, name: str, content_type: str) -> web.StreamResponse:
        path = OBS_DIR / name
        if not path.exists():
            return web.Response(status=404, text=f"{name} not found")
        return web.Response(
            body=path.read_bytes(),
            content_type=content_type.split(";")[0],
            charset="utf-8",
        )

    @staticmethod
    def _json_response(data: Any, *, status: int = 200) -> web.Response:
        return web.Response(
            text=json.dumps(data, ensure_ascii=False),
            content_type="application/json",
            charset="utf-8",
            status=status,
        )

    @staticmethod
    def _error(message: str, *, status: int = 400) -> web.Response:
        return AdminServer._json_response({"error": message}, status=status)

    async def _read_json(self, request: web.Request) -> Optional[dict]:
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return data

    @staticmethod
    def _parse_balance(raw: Any) -> Optional[int]:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        if value < 0:
            return None
        return value

    @staticmethod
    def _parse_user_id(raw: Any) -> Optional[str]:
        if not isinstance(raw, str):
            return None
        uid = raw.strip()
        if not uid:
            return None
        return uid

    async def _api_points_list(self, request: web.Request) -> web.Response:
        items = await points_db.list_all(self._db)
        return self._json_response({"items": items})

    async def _api_points_get(self, request: web.Request) -> web.Response:
        user_id = request.match_info["user_id"]
        balance = await points_db.get_balance(self._db, user_id)
        row = await self._db.fetchone(
            "SELECT 1 FROM points WHERE user_id = ?",
            (user_id,),
        )
        if row is None:
            return self._error("Пользователь не найден", status=404)
        return self._json_response({"user_id": user_id, "balance": balance})

    async def _api_points_create(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        if data is None:
            return self._error("Некорректный JSON")
        user_id = self._parse_user_id(data.get("user_id"))
        balance = self._parse_balance(data.get("balance", 0))
        if user_id is None:
            return self._error("user_id обязателен")
        if balance is None:
            return self._error("balance должен быть целым числом >= 0")
        existing = await self._db.fetchone(
            "SELECT 1 FROM points WHERE user_id = ?",
            (user_id,),
        )
        if existing is not None:
            return self._error("Пользователь уже существует", status=409)
        await points_db.set_balance(self._db, user_id, balance)
        return self._json_response({"user_id": user_id, "balance": balance}, status=201)

    async def _api_points_update(self, request: web.Request) -> web.Response:
        user_id = request.match_info["user_id"]
        data = await self._read_json(request)
        if data is None:
            return self._error("Некорректный JSON")
        balance = self._parse_balance(data.get("balance"))
        if balance is None:
            return self._error("balance должен быть целым числом >= 0")
        existing = await self._db.fetchone(
            "SELECT 1 FROM points WHERE user_id = ?",
            (user_id,),
        )
        if existing is None:
            return self._error("Пользователь не найден", status=404)
        await points_db.set_balance(self._db, user_id, balance)
        return self._json_response({"user_id": user_id, "balance": balance})

    async def _api_points_delete(self, request: web.Request) -> web.Response:
        user_id = request.match_info["user_id"]
        deleted = await points_db.delete_user(self._db, user_id)
        if not deleted:
            return self._error("Пользователь не найден", status=404)
        return self._json_response({"deleted": True, "user_id": user_id})

    async def _api_queue_get(self, request: web.Request) -> web.Response:
        playing = asdict(self._queue.current) if self._queue.current else None
        waiting = self._queue.list_waiting()
        return self._json_response({"playing": playing, "waiting": waiting})

    async def _api_queue_delete(self, request: web.Request) -> web.Response:
        try:
            index = int(request.match_info["index"])
        except ValueError:
            return self._error("index должен быть целым числом")
        removed = await self._queue.remove_waiting(index)
        if not removed:
            return self._error("Трек не найден", status=404)
        return self._json_response({"deleted": True, "index": index})

    async def _api_sr_get(self, request: web.Request) -> web.Response:
        return self._json_response({"orders_enabled": self._sr.orders_enabled})

    async def _api_sr_put(self, request: web.Request) -> web.Response:
        data = await self._read_json(request)
        if data is None:
            return self._error("Некорректный JSON")
        raw = data.get("orders_enabled")
        if not isinstance(raw, bool):
            return self._error("orders_enabled должен быть true или false")
        await self._sr.set_orders_enabled(raw)
        return self._json_response({"orders_enabled": self._sr.orders_enabled})
