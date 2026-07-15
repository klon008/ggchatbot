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
from bot.web.static import serve_obs_asset, serve_obs_card_template, serve_obs_file

if TYPE_CHECKING:
    from bot.economy.points import PointsStore
    from bot.races.handler import RacesHandler
    from bot.roulette.handler import RouletteHandler
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
        roulette_handler: "RouletteHandler",
        races_handler: "RacesHandler",
    ) -> None:
        self._db = db
        self._queue = queue
        self._sr = sr_handler
        self._roulette = roulette_handler
        self._races = races_handler
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
                web.get("/cards-admin.html", self._handle_cards_admin_html),
                web.get("/cards-admin.js", self._handle_cards_admin_js),
                web.get("/promo-generator.html", self._handle_promo_generator_html),
                web.get("/promo-generator.js", self._handle_promo_generator_js),
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
                web.get("/api/roulette", self._api_roulette_get),
                web.put("/api/roulette", self._api_roulette_put),
                web.post("/api/roulette/open", self._api_roulette_open),
                web.post("/api/roulette/spin", self._api_roulette_spin),
                web.post("/api/roulette/bank", self._api_roulette_bank),
                web.post("/api/roulette/cancel", self._api_roulette_cancel),
                web.get("/roulette.html", self._handle_roulette_html),
                web.get("/roulette.js", self._handle_roulette_js),
                web.get("/api/races", self._api_races_get),
                web.put("/api/races", self._api_races_put),
                web.post("/api/races/open", self._api_races_open),
                web.post("/api/races/start", self._api_races_start),
                web.post("/api/races/bank", self._api_races_bank),
                web.post("/api/races/cancel", self._api_races_cancel),
                web.get("/races.html", self._handle_races_html),
                web.get("/races.js", self._handle_races_js),
                web.get("/card-templates/{path:.*}", self._handle_card_templates),
                web.get("/assets/{path:.*}", self._handle_assets),
            ]
        )

    async def _handle_index(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("admin.html", "text/html; charset=utf-8")

    async def _handle_admin_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("admin.js", "application/javascript; charset=utf-8")

    async def _handle_cards_admin_html(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("cards-admin.html", "text/html; charset=utf-8")

    async def _handle_cards_admin_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("cards-admin.js", "application/javascript; charset=utf-8")

    async def _handle_promo_generator_html(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("promo-generator.html", "text/html; charset=utf-8")

    async def _handle_promo_generator_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file(
            "promo-generator.js", "application/javascript; charset=utf-8"
        )

    async def _handle_roulette_html(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("roulette.html", "text/html; charset=utf-8")

    async def _handle_roulette_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("roulette.js", "application/javascript; charset=utf-8")

    async def _handle_races_html(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("races.html", "text/html; charset=utf-8")

    async def _handle_races_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("races.js", "application/javascript; charset=utf-8")

    async def _handle_assets(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_asset(request.match_info["path"])

    async def _handle_card_templates(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_card_template(request.match_info["path"])

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

    async def _api_roulette_get(self, request: web.Request) -> web.Response:
        return json_response(await self._roulette.get_status())

    async def _api_roulette_put(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        if "auto_enabled" in data:
            if not isinstance(data["auto_enabled"], bool):
                return error_response("auto_enabled должен быть true или false")
            await self._roulette.set_auto_enabled(data["auto_enabled"])
        collect_sec = data.get("collect_sec")
        cooldown_sec = data.get("cooldown_sec")
        if collect_sec is not None or cooldown_sec is not None:
            status = await self._roulette.get_status()
            new_collect = collect_sec if collect_sec is not None else status["collect_sec"]
            new_cooldown = cooldown_sec if cooldown_sec is not None else status["cooldown_sec"]
            if not isinstance(new_collect, int) or new_collect < 10:
                return error_response("collect_sec должен быть целым числом >= 10")
            if not isinstance(new_cooldown, int) or new_cooldown < 10:
                return error_response("cooldown_sec должен быть целым числом >= 10")
            await self._roulette.set_timers(new_collect, new_cooldown)
        return json_response(await self._roulette.get_status())

    async def _api_roulette_open(self, request: web.Request) -> web.Response:
        try:
            await self._roulette.admin_open()
        except RuntimeError as exc:
            code = str(exc)
            messages = {
                "auto_mode": "Доступно только при выключенной авто-рулетке",
                "not_idle": "Стол уже открыт или идёт раунд",
                "bank_low": "В казне недостаточно баллов для старта",
                "cooldown": "Рулетка на перезарядке",
            }
            return error_response(messages.get(code, code), status=409)
        return json_response(await self._roulette.get_status())

    async def _api_roulette_spin(self, request: web.Request) -> web.Response:
        try:
            await self._roulette.admin_spin()
        except RuntimeError as exc:
            if str(exc) == "not_open":
                return error_response("Ставки не открыты", status=409)
            raise
        return json_response(await self._roulette.get_status())

    async def _api_roulette_bank(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        amount = data.get("amount")
        if not isinstance(amount, int) or amount <= 0:
            return error_response("amount должен быть целым числом > 0")
        try:
            await self._roulette.admin_top_up_bank(amount)
        except ValueError:
            return error_response("amount должен быть целым числом > 0")
        return json_response(await self._roulette.get_status())

    async def _api_roulette_cancel(self, request: web.Request) -> web.Response:
        try:
            await self._roulette.admin_cancel()
        except RuntimeError as exc:
            if str(exc) == "not_open":
                return error_response("Нет открытого раунда для отмены", status=409)
            raise
        return json_response(await self._roulette.get_status())

    async def _api_races_get(self, request: web.Request) -> web.Response:
        return json_response(await self._races.get_status())

    async def _api_races_put(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        if "auto_enabled" in data:
            if not isinstance(data["auto_enabled"], bool):
                return error_response("auto_enabled должен быть true или false")
            await self._races.set_auto_enabled(data["auto_enabled"])
        collect_sec = data.get("collect_sec")
        cooldown_sec = data.get("cooldown_sec")
        race_delay_sec = data.get("race_delay_sec")
        if collect_sec is not None or cooldown_sec is not None or race_delay_sec is not None:
            status = await self._races.get_status()
            new_collect = collect_sec if collect_sec is not None else status["collect_sec"]
            new_cooldown = cooldown_sec if cooldown_sec is not None else status["cooldown_sec"]
            new_delay = race_delay_sec if race_delay_sec is not None else status["race_delay_sec"]
            if not isinstance(new_collect, int) or new_collect < 10:
                return error_response("collect_sec должен быть целым числом >= 10")
            if not isinstance(new_cooldown, int) or new_cooldown < 10:
                return error_response("cooldown_sec должен быть целым числом >= 10")
            if not isinstance(new_delay, int) or new_delay < 0:
                return error_response("race_delay_sec должен быть целым числом >= 0")
            await self._races.set_timers(new_collect, new_cooldown, new_delay)
        return json_response(await self._races.get_status())

    async def _api_races_open(self, request: web.Request) -> web.Response:
        try:
            await self._races.admin_open()
        except RuntimeError as exc:
            code = str(exc)
            messages = {
                "auto_mode": "Доступно только при выключенных авто-скачках",
                "not_idle": "Забег уже открыт или идёт раунд",
                "bank_low": "В казне недостаточно баллов для старта",
                "cooldown": "Скачки на перезарядке",
            }
            return error_response(messages.get(code, code), status=409)
        return json_response(await self._races.get_status())

    async def _api_races_start(self, request: web.Request) -> web.Response:
        try:
            await self._races.admin_start()
        except RuntimeError as exc:
            if str(exc) == "not_open":
                return error_response("Ставки не открыты", status=409)
            raise
        return json_response(await self._races.get_status())

    async def _api_races_bank(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        amount = data.get("amount")
        if not isinstance(amount, int) or amount <= 0:
            return error_response("amount должен быть целым числом > 0")
        try:
            await self._races.admin_top_up_bank(amount)
        except ValueError:
            return error_response("amount должен быть целым числом > 0")
        return json_response(await self._races.get_status())

    async def _api_races_cancel(self, request: web.Request) -> web.Response:
        try:
            await self._races.admin_cancel()
        except RuntimeError as exc:
            if str(exc) == "not_open":
                return error_response("Нет открытого забега для отмены", status=409)
            raise
        return json_response(await self._races.get_status())
