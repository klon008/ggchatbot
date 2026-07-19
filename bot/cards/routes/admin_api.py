"""Admin API для бустеров и тиражей (localhost OBS, порт 8765)."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

from bot.cards.card_stories import STORIES_SOURCE_REL, load_card_stories
from bot.cards.series_pack.conflicts import check_step_conflicts
from bot.cards.series_pack.models import (
    DEFAULT_CARD_BACK_ID,
    MAX_UPLOAD_BYTES,
    RARITIES,
    RARITY_COLORS,
)
from bot.cards.series_pack.service import (
    ImportBusyError,
    build_pack_zip,
    draft_from_meta,
    import_pack_zip,
)
from bot.db import cards as cards_db
from bot.web.api import error_response, json_response, read_json
from config import Config

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
                web.get("/api/cards/series-pack/config", self._series_pack_config),
                web.post("/api/cards/series-pack/check", self._series_pack_check),
                web.post("/api/cards/series-pack/build", self._series_pack_build),
                web.post("/api/cards/series-pack/import", self._series_pack_import),
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

    async def _series_pack_config(self, request: web.Request) -> web.Response:
        cfg = Config.load()
        return json_response(
            {
                "frontend_root": cfg.frontend_root,
                "rarities": list(RARITIES),
                "rarity_colors": dict(RARITY_COLORS),
                "max_upload_bytes": MAX_UPLOAD_BYTES,
                "default_card_back_id": DEFAULT_CARD_BACK_ID,
            }
        )

    async def _series_pack_check(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        try:
            step = int(data.get("step", -1))
        except (TypeError, ValueError):
            return error_response("step должен быть 0–3")
        if step not in (0, 1, 2, 3):
            return error_response("step должен быть 0–3")
        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = {k: v for k, v in data.items() if k != "step"}
        errs = await check_step_conflicts(self._db, step=step, payload=payload)
        return json_response({"ok": not errs, "errors": errs})

    def _check_upload_size(self, request: web.Request) -> Optional[web.Response]:
        cl = request.headers.get("Content-Length")
        if cl is not None:
            try:
                if int(cl) > MAX_UPLOAD_BYTES:
                    return error_response(
                        f"Слишком большой upload (лимит {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
                        status=413,
                    )
            except ValueError:
                pass
        return None

    async def _series_pack_build(self, request: web.Request) -> web.StreamResponse:
        oversized = self._check_upload_size(request)
        if oversized is not None:
            return oversized

        if not request.content_type.startswith("multipart/"):
            return error_response("Ожидается multipart/form-data")

        tmp = Path(tempfile.mkdtemp(prefix="series-pack-build-"))
        try:
            meta: Optional[dict[str, Any]] = None
            back_path: Optional[Path] = None
            card_paths: dict[str, Path] = {}

            reader = await request.multipart()
            while True:
                part = await reader.next()
                if part is None:
                    break
                name = part.name or ""
                if name == "meta":
                    raw = await part.text()
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        return error_response("meta: некорректный JSON")
                    if not isinstance(parsed, dict):
                        return error_response("meta: ожидается объект")
                    meta = parsed
                elif name == "back":
                    data = await part.read(decode=False)
                    if len(data) > MAX_UPLOAD_BYTES:
                        return error_response("Файл рубашки слишком большой", status=413)
                    back_path = tmp / "back.svg"
                    back_path.write_bytes(data)
                elif name.startswith("card_"):
                    cid = name[5:].strip().lower()
                    data = await part.read(decode=False)
                    if not cid:
                        continue
                    # keep original suffix if any
                    filename = part.filename or f"{cid}.png"
                    suffix = Path(filename).suffix.lower() or ".png"
                    dest = tmp / f"{cid}{suffix}"
                    dest.write_bytes(data)
                    card_paths[cid] = dest

            if meta is None:
                return error_response("Нужно поле meta (JSON)")

            draft = draft_from_meta(meta, back_path=back_path, card_paths=card_paths)
            out_dir = tmp / "out"
            zip_path, errs = build_pack_zip(draft, out_dir)
            if errs or zip_path is None:
                return json_response({"ok": False, "errors": errs}, status=400)

            body = zip_path.read_bytes()
            return web.Response(
                body=body,
                status=200,
                headers={
                    "Content-Type": "application/zip",
                    "Content-Disposition": f'attachment; filename="{zip_path.name}"',
                },
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    async def _series_pack_import(self, request: web.Request) -> web.Response:
        oversized = self._check_upload_size(request)
        if oversized is not None:
            return oversized

        if not request.content_type.startswith("multipart/"):
            return error_response("Ожидается multipart/form-data")

        cfg = Config.load()
        tmp = Path(tempfile.mkdtemp(prefix="series-pack-import-"))
        try:
            zip_path: Optional[Path] = None
            apply_frontend = False
            frontend_root_raw = cfg.frontend_root
            dry_run = False

            reader = await request.multipart()
            while True:
                part = await reader.next()
                if part is None:
                    break
                name = part.name or ""
                if name == "file":
                    data = await part.read(decode=False)
                    if len(data) > MAX_UPLOAD_BYTES:
                        return error_response("ZIP слишком большой", status=413)
                    zip_path = tmp / "pack.zip"
                    zip_path.write_bytes(data)
                elif name == "apply_frontend":
                    apply_frontend = (await part.text()).strip() in ("1", "true", "yes", "on")
                elif name == "frontend_root":
                    frontend_root_raw = (await part.text()).strip()
                elif name == "dry_run":
                    dry_run = (await part.text()).strip() in ("1", "true", "yes", "on")

            if zip_path is None or not zip_path.is_file():
                return error_response("Нужен файл file (.zip)")

            fe_path = Path(frontend_root_raw) if frontend_root_raw else None
            try:
                result = await import_pack_zip(
                    zip_path,
                    self._db,
                    apply_frontend_flag=apply_frontend,
                    frontend_root=fe_path if apply_frontend else None,
                    dry_run=dry_run,
                )
            except ImportBusyError as exc:
                return json_response(
                    {"ok": False, "errors": [str(exc)]},
                    status=409,
                )
            except Exception as exc:
                return json_response(
                    {"ok": False, "errors": [str(exc)]},
                    status=500,
                )

            status = 200 if result.get("ok") else 400
            return json_response(result, status=status)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
