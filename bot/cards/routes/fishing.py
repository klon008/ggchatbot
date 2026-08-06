"""HTTP-маршруты read-only Fishing API (топы недели + абсолютные трофеи)."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

from bot.fishing.storage import FishingStorage
from bot.web.api import error_response, json_response

from ..constants import ALBUM_API_RATE_LIMIT_PER_MIN
from .album import resolve_cors_origin

if TYPE_CHECKING:
    from bot.db import Database


def _public_catch(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "species": str(row.get("species") or ""),
        "user_name": str(row.get("user_name") or ""),
        "weight": float(row.get("weight") or 0),
        "achieved_at": float(row.get("achieved_at") or 0),
    }


class FishingApiRoutes:
    def __init__(
        self,
        db: "Database",
        cors_origins: tuple[str, ...],
    ) -> None:
        self._store = FishingStorage(db)
        self._cors_origins = cors_origins
        self._hits: dict[str, list[float]] = defaultdict(list)

    def register(self, app: web.Application) -> None:
        app.router.add_get("/api/v1/fishing", self._fishing)
        app.router.add_route("OPTIONS", "/api/v1/fishing", self._options)

    def _cors_origin(self, request: web.Request) -> Optional[str]:
        return resolve_cors_origin(request, self._cors_origins)

    def _with_cors(self, request: web.Request, response: web.Response) -> web.Response:
        origin = self._cors_origin(request)
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    async def _options(self, request: web.Request) -> web.Response:
        return self._with_cors(request, web.Response(status=204))

    def _rate_limited(self, request: web.Request) -> bool:
        ip = request.remote or "unknown"
        now = time.time()
        window = self._hits[ip]
        window[:] = [t for t in window if now - t < 60.0]
        if len(window) >= ALBUM_API_RATE_LIMIT_PER_MIN:
            return True
        window.append(now)
        return False

    async def _fishing(self, request: web.Request) -> web.Response:
        if self._rate_limited(request):
            return self._with_cors(request, error_response("rate limit", status=429))

        await self._store.ensure_calendar()
        meta = await self._store.meta()
        leaders, fish_of_week = await self._store.week_top()
        trophies = await self._store.list_trophies()

        payload = {
            "v": 1,
            "week_id": str(meta.get("current_week_id") or ""),
            "week_leaders": [_public_catch(r) for r in leaders],
            "fish_of_week": _public_catch(fish_of_week) if fish_of_week else None,
            "trophies": [_public_catch(r) for r in trophies],
        }
        return self._with_cors(request, json_response(payload))
