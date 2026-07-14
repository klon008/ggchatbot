"""Admin API для бустеров и тиражей (localhost OBS, порт 8765)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

from bot.cards.card_stories import STORIES_SOURCE_REL, load_card_stories
from bot.db import cards as cards_db
from bot.web.api import error_response, json_response, read_json

if TYPE_CHECKING:
    from bot.db import Database

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_PROMO_URL_RE = re.compile(r"^(https?://|/assets/).+", re.IGNORECASE)
_DEFAULT_WEIGHTS = {
    "common": 48.0,
    "uncommon": 24.0,
    "rare": 12.0,
    "epic": 7.0,
    "legendary": 5.0,
    "mythic": 1.0,
    "secretRare": 1.0,
}


def _parse_slug(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    slug = raw.strip().lower()
    if not _SLUG_RE.match(slug):
        return None
    return slug


def _parse_weights(raw: Any) -> Optional[dict[str, float]]:
    if raw is None:
        return dict(_DEFAULT_WEIGHTS)
    if not isinstance(raw, dict):
        return None
    out: dict[str, float] = {}
    for key in cards_db.RARITIES:
        if key not in raw:
            return None
        try:
            out[key] = float(raw[key])
        except (TypeError, ValueError):
            return None
    return out


class CardsAdminRoutes:
    def __init__(self, db: "Database") -> None:
        self._db = db

    def register(self, app: web.Application) -> None:
        app.add_routes(
            [
                web.get("/api/cards/catalog", self._catalog),
                web.get("/api/cards/meta", self._meta_get),
                web.put("/api/cards/meta", self._meta_put),
                web.get("/api/cards/series", self._series_list),
                web.put("/api/cards/series/{series_id}", self._series_update),
                web.get("/api/cards/boosters", self._boosters_list),
                web.post("/api/cards/boosters", self._boosters_create),
                web.put("/api/cards/boosters/{booster_id}", self._boosters_update),
                web.put("/api/cards/boosters/{booster_id}/promo", self._boosters_promo),
                web.get("/api/cards/draws", self._draws_list),
                web.post("/api/cards/draws", self._draws_create),
                web.post("/api/cards/draws/{draw_id}/activate", self._draws_activate),
                web.post("/api/cards/draws/{draw_id}/pause", self._draws_pause),
                web.post("/api/cards/draws/{draw_id}/close", self._draws_close),
                web.post("/api/cards/draws/{draw_id}/copy", self._draws_copy),
            ]
        )

    async def _catalog(self, request: web.Request) -> web.Response:
        items = await cards_db.list_catalog_cards(self._db)
        stories = load_card_stories()
        for item in items:
            item["story"] = stories.get(str(item.get("id") or ""), "")
        return json_response(
            {
                "items": items,
                "stories_source": STORIES_SOURCE_REL,
                "stories_loaded": bool(stories),
                "stories_count": len(stories),
            }
        )

    async def _meta_get(self, request: web.Request) -> web.Response:
        return json_response(await cards_db.get_cards_meta(self._db))

    async def _meta_put(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        kwargs: dict[str, Any] = {}
        if "daily_open_limit" in data:
            try:
                limit = int(data["daily_open_limit"])
            except (TypeError, ValueError):
                return error_response("daily_open_limit должен быть целым >= 0")
            if limit < 0:
                return error_response("daily_open_limit должен быть >= 0")
            kwargs["daily_open_limit"] = limit
        if "enabled" in data:
            raw = data["enabled"]
            if not isinstance(raw, bool):
                return error_response("enabled должен быть true или false")
            kwargs["enabled"] = raw
        if "anim_speed" in data:
            try:
                speed = float(data["anim_speed"])
            except (TypeError, ValueError):
                return error_response("anim_speed должен быть числом 0.5–3.0")
            if speed < cards_db.ANIM_SPEED_MIN or speed > cards_db.ANIM_SPEED_MAX:
                return error_response("anim_speed должен быть в диапазоне 0.5–3.0")
            kwargs["anim_speed"] = speed
        if not kwargs:
            return error_response("Нужен daily_open_limit, enabled и/или anim_speed")
        return json_response(await cards_db.set_cards_meta(self._db, **kwargs))

    async def _series_list(self, request: web.Request) -> web.Response:
        items = await cards_db.list_series(self._db)
        return json_response({"items": items})

    async def _series_update(self, request: web.Request) -> web.Response:
        series_id = request.match_info["series_id"]
        if not await cards_db.series_exists(self._db, series_id):
            return error_response("Серия не найдена", status=404)
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        name = str(data.get("name", "")).strip()
        if not name:
            return error_response("name обязателен")
        try:
            sort_order = int(data.get("sort_order", 0))
        except (TypeError, ValueError):
            return error_response("sort_order должен быть целым")
        card_back_id = str(data.get("card_back_id", "card-back")).strip()
        if not card_back_id or not _SLUG_RE.match(card_back_id):
            return error_response("card_back_id: латиница, цифры, -, _ (до 32 символов)")
        updated = await cards_db.update_series(
            self._db,
            series_id=series_id,
            name=name,
            sort_order=sort_order,
            card_back_id=card_back_id,
        )
        return json_response(updated or {"id": series_id})

    async def _boosters_list(self, request: web.Request) -> web.Response:
        items = await cards_db.list_boosters(self._db)
        return json_response({"items": items})

    async def _boosters_create(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        booster_id = _parse_slug(data.get("id"))
        name = str(data.get("name", "")).strip()
        card_ids = data.get("card_ids")
        if booster_id is None:
            return error_response("id: латиница, цифры, -, _ (до 32 символов)")
        if not name:
            return error_response("name обязателен")
        if not isinstance(card_ids, list) or not card_ids:
            return error_response("card_ids: непустой список slug карт")
        ids = [str(c).strip() for c in card_ids if str(c).strip()]
        if await cards_db.booster_exists(self._db, booster_id):
            return error_response("Бустер уже существует", status=409)
        await cards_db.create_booster(
            self._db, booster_id=booster_id, name=name, card_ids=ids
        )
        items = await cards_db.list_boosters(self._db)
        created = next((b for b in items if b["id"] == booster_id), None)
        return json_response(created or {"id": booster_id}, status=201)

    async def _boosters_update(self, request: web.Request) -> web.Response:
        booster_id = request.match_info["booster_id"]
        if not await cards_db.booster_exists(self._db, booster_id):
            return error_response("Бустер не найден", status=404)
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        name = str(data.get("name", "")).strip()
        card_ids = data.get("card_ids")
        if not name:
            return error_response("name обязателен")
        if not isinstance(card_ids, list) or not card_ids:
            return error_response("card_ids: непустой список")
        ids = [str(c).strip() for c in card_ids if str(c).strip()]
        await cards_db.update_booster(
            self._db, booster_id=booster_id, name=name, card_ids=ids
        )
        items = await cards_db.list_boosters(self._db)
        updated = next((b for b in items if b["id"] == booster_id), None)
        return json_response(updated or {"id": booster_id})

    async def _boosters_promo(self, request: web.Request) -> web.Response:
        booster_id = request.match_info["booster_id"]
        if not await cards_db.booster_exists(self._db, booster_id):
            return error_response("Бустер не найден", status=404)
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        raw = data.get("promo_image_url", "")
        if raw is None:
            raw = ""
        if not isinstance(raw, str):
            return error_response("promo_image_url должен быть строкой")
        url = raw.strip()
        if not url:
            await cards_db.set_booster_promo_url(self._db, booster_id, None)
            return json_response({"promo_image_url": None})
        if len(url) > 2048:
            return error_response("promo_image_url слишком длинный")
        if not _PROMO_URL_RE.match(url):
            return error_response(
                "promo_image_url: нужна http(s)://… или путь /assets/…"
            )
        await cards_db.set_booster_promo_url(self._db, booster_id, url)
        return json_response({"promo_image_url": url})

    async def _draws_list(self, request: web.Request) -> web.Response:
        items = await cards_db.list_draws(self._db)
        return json_response({"items": items})

    async def _draws_create(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        draw_id = _parse_slug(data.get("id"))
        booster_id = _parse_slug(data.get("booster_id"))
        name = str(data.get("name", "")).strip()
        if draw_id is None:
            return error_response("id: slug тиража")
        if booster_id is None or not await cards_db.booster_exists(self._db, booster_id):
            return error_response("booster_id не найден")
        if not name:
            return error_response("name обязателен")
        try:
            cost = int(data.get("cost_points", 0))
            cards_per = int(data.get("cards_per_open", 1))
            daily_limit = int(data.get("daily_limit", 0))
        except (TypeError, ValueError):
            return error_response("cost_points, cards_per_open, daily_limit — целые числа")
        if cost <= 0 or cards_per <= 0:
            return error_response("cost_points и cards_per_open > 0")
        weights = _parse_weights(data.get("rarity_weights"))
        if weights is None:
            return error_response("rarity_weights: объект с редкостями common…secretRare (+ mythic)")
        if await cards_db.draw_exists(self._db, draw_id):
            return error_response("Тираж уже существует", status=409)
        activate = bool(data.get("activate", False))
        await cards_db.create_draw(
            self._db,
            draw_id=draw_id,
            booster_id=booster_id,
            name=name,
            cost_points=cost,
            cards_per_open=cards_per,
            rarity_weights=weights,
            daily_limit=max(0, daily_limit),
            activate=activate,
        )
        item = await cards_db.get_draw(self._db, draw_id)
        return json_response(item, status=201)

    async def _draws_activate(self, request: web.Request) -> web.Response:
        draw_id = request.match_info["draw_id"]
        try:
            item = await cards_db.activate_draw(self._db, draw_id)
        except ValueError as exc:
            code = str(exc)
            messages = {
                "not_found": ("Тираж не найден", 404),
                "closed": ("Завершённый тираж нельзя активировать", 409),
                "already_active": ("Тираж уже активен", 409),
                "not_queued": ("Активировать можно только очередь или паузу", 409),
                "not_next": (
                    "FIFO: активировать можно только следующий тираж в очереди "
                    "(и только если нет активного/на паузе)",
                    409,
                ),
                "busy": ("Сейчас уже есть активный или приостановленный тираж", 409),
            }
            msg, status = messages.get(code, (code, 409))
            return error_response(msg, status=status)
        return json_response(item)

    async def _draws_pause(self, request: web.Request) -> web.Response:
        draw_id = request.match_info["draw_id"]
        try:
            item = await cards_db.pause_draw(self._db, draw_id)
        except ValueError as exc:
            code = str(exc)
            if code == "not_found":
                return error_response("Тираж не найден", status=404)
            if code == "not_active":
                return error_response("На паузу можно поставить только активный тираж", status=409)
            return error_response(code, status=409)
        return json_response(item)

    async def _draws_close(self, request: web.Request) -> web.Response:
        draw_id = request.match_info["draw_id"]
        try:
            item = await cards_db.close_draw(self._db, draw_id, promote=True)
        except ValueError as exc:
            code = str(exc)
            if code == "not_found":
                return error_response("Тираж не найден", status=404)
            if code == "not_live":
                return error_response(
                    "Завершить можно только активный или приостановленный тираж",
                    status=409,
                )
            return error_response(code, status=409)
        return json_response(item)

    async def _draws_copy(self, request: web.Request) -> web.Response:
        source_id = request.match_info["draw_id"]
        data = await read_json(request) or {}
        new_id = _parse_slug(data.get("id"))
        new_name = str(data.get("name", "")).strip()
        if new_id is None:
            return error_response("id нового тиража обязателен")
        if not new_name:
            return error_response("name обязателен")
        if await cards_db.draw_exists(self._db, new_id):
            return error_response("Тираж с таким id уже есть", status=409)
        try:
            await cards_db.copy_draw(
                self._db,
                source_id,
                new_id,
                new_name,
                activate=bool(data.get("activate", False)),
            )
        except ValueError:
            return error_response("Исходный тираж не найден", status=404)
        item = await cards_db.get_draw(self._db, new_id)
        return json_response(item, status=201)
