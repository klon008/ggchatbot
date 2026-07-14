"""HTTP-маршруты read-only Album API."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

from aiohttp import web

from bot.db import cards as cards_db
from bot.web.api import error_response, json_response

from ..album_token import verify_album_token
from ..constants import ALBUM_API_RATE_LIMIT_PER_MIN

if TYPE_CHECKING:
    from bot.db import Database


class AlbumApiRoutes:
    def __init__(
        self,
        db: "Database",
        link_secret: str,
        cors_origins: tuple[str, ...],
    ) -> None:
        self._db = db
        self._link_secret = link_secret
        self._cors_origins = cors_origins
        self._hits: dict[str, list[float]] = defaultdict(list)

    def register(self, app: web.Application) -> None:
        app.router.add_get("/api/v1/health", self._health)
        app.router.add_get("/api/v1/album", self._album)
        app.router.add_route("OPTIONS", "/api/v1/album", self._options)
        app.router.add_route("OPTIONS", "/api/v1/health", self._options)

    def _cors_origin(self, request: web.Request) -> Optional[str]:
        origin = request.headers.get("Origin", "")
        if not origin:
            return self._cors_origins[0] if self._cors_origins else "*"
        for allowed in self._cors_origins:
            if allowed == "*":
                return origin
            if origin == allowed or (
                allowed.startswith("https://") and origin.endswith(allowed.removeprefix("https://"))
            ):
                return origin
        if "github.io" in origin:
            return origin
        return self._cors_origins[0] if self._cors_origins else None

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

    async def _health(self, request: web.Request) -> web.Response:
        if self._rate_limited(request):
            return self._with_cors(request, error_response("rate limit", status=429))
        return self._with_cors(request, json_response({"ok": True}))

    async def _album(self, request: web.Request) -> web.Response:
        if self._rate_limited(request):
            return self._with_cors(request, error_response("rate limit", status=429))

        nick = (request.query.get("u") or "").strip().lower()
        token = (request.query.get("k") or "").strip()
        exp_raw = (request.query.get("exp") or "").strip()

        if not nick or not token or not exp_raw:
            return self._with_cors(request, error_response("missing params", status=400))

        try:
            exp = int(exp_raw)
        except ValueError:
            return self._with_cors(request, error_response("invalid exp", status=400))

        if not self._link_secret:
            return self._with_cors(request, error_response("api not configured", status=503))

        if not verify_album_token(self._link_secret, nick, exp, token):
            return self._with_cors(request, error_response("invalid token", status=401))

        user_id = await cards_db.get_user_id_by_nick(self._db, nick)
        if user_id is None:
            return self._with_cors(request, error_response("player not found", status=404))

        display_name = await cards_db.get_user_name(self._db, user_id)
        series = await cards_db.count_series_progress(self._db, user_id)
        collection = await cards_db.count_collection(self._db, user_id)
        owned = await cards_db.list_owned_cards(self._db, user_id)

        cards_payload = [
            {
                "id": c.id,
                "name": c.name,
                "rarity": c.rarity,
                "series_id": c.series_id,
                "card_back_id": c.card_back_id or "card-back",
                "d": c.obtained_at,
                "b": (
                    f"Бустер «{c.booster_name}» · {c.draw_name}"
                    if c.booster_name or c.draw_name
                    else ""
                ),
                "image_url": c.image_url,
            }
            for c in owned
        ]

        payload = {
            "v": 1,
            "u": display_name or nick,
            "series": [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "owned": s["owned"],
                    "total": s["total"],
                    "card_back_id": s.get("card_back_id") or "card-back",
                }
                for s in series
            ],
            "collection": collection,
            "cards": cards_payload,
        }
        return self._with_cors(request, json_response(payload))


def parse_cors_origins(site_base_url: str) -> tuple[str, ...]:
    parsed = urlparse(site_base_url)
    if parsed.scheme and parsed.netloc:
        return (f"{parsed.scheme}://{parsed.netloc}",)
    return ("https://dartvalkkiprincess.github.io",)
