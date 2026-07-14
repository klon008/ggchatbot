"""Admin API для бустеров и тиражей (localhost OBS, порт 8765)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

from bot.cards.card_stories import STORIES_SOURCE_REL, load_card_stories
from bot.db import cards as cards_db
from bot.web.api import error_response, json_response, read_json
from bot.web.static import OBS_ASSETS_DIR

if TYPE_CHECKING:
    from bot.db import Database

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_BOOSTERS_DIR = OBS_ASSETS_DIR / "boosters"
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
                web.get("/api/cards/boosters", self._boosters_list),
                web.post("/api/cards/boosters", self._boosters_create),
                web.put("/api/cards/boosters/{booster_id}", self._boosters_update),
                web.post("/api/cards/boosters/{booster_id}/promo", self._boosters_promo),
                web.get("/api/cards/draws", self._draws_list),
                web.post("/api/cards/draws", self._draws_create),
                web.post("/api/cards/draws/{draw_id}/activate", self._draws_activate),
                web.post("/api/cards/draws/{draw_id}/pause", self._draws_pause),
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
        limit = await cards_db.get_global_daily_limit(self._db)
        return json_response({"daily_open_limit": limit})

    async def _meta_put(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        try:
            limit = int(data.get("daily_open_limit", 0))
        except (TypeError, ValueError):
            return error_response("daily_open_limit должен быть целым >= 0")
        if limit < 0:
            return error_response("daily_open_limit должен быть >= 0")
        await cards_db.set_global_daily_limit(self._db, limit)
        return json_response({"daily_open_limit": limit})

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

        reader = await request.multipart()
        field = await reader.next()
        if field is None or field.name != "file":
            return error_response("Ожидается multipart field 'file'")

        filename = (field.filename or "").lower()
        if not filename.endswith((".jpg", ".jpeg", ".webp", ".png")):
            return error_response("Допустимы jpg, png, webp")

        data = await field.read()
        if len(data) > 8 * 1024 * 1024:
            return error_response("Файл слишком большой (макс. 8 МБ)")

        ext = ".jpg"
        if filename.endswith(".png"):
            ext = ".png"
        elif filename.endswith(".webp"):
            ext = ".webp"

        _BOOSTERS_DIR.mkdir(parents=True, exist_ok=True)
        dest = _BOOSTERS_DIR / f"{booster_id}{ext}"
        dest.write_bytes(data)

        promo_url = f"/assets/boosters/{booster_id}{ext}"
        await cards_db.set_booster_promo_url(self._db, booster_id, promo_url)
        return json_response({"promo_image_url": promo_url})

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
        if not await cards_db.draw_exists(self._db, draw_id):
            return error_response("Тираж не найден", status=404)
        await cards_db.set_draw_status(self._db, draw_id, cards_db.DRAW_ACTIVE)
        item = await cards_db.get_draw(self._db, draw_id)
        return json_response(item)

    async def _draws_pause(self, request: web.Request) -> web.Response:
        draw_id = request.match_info["draw_id"]
        if not await cards_db.draw_exists(self._db, draw_id):
            return error_response("Тираж не найден", status=404)
        await cards_db.set_draw_status(self._db, draw_id, cards_db.DRAW_PAUSED)
        item = await cards_db.get_draw(self._db, draw_id)
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
