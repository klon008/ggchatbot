"""Отдельный локальный HTTP-сервер для read-only Album API."""

from __future__ import annotations

import logging
from typing import Optional

from aiohttp import web

from bot.web.server import LocalWebServer

from .constants import ALBUM_API_HOST, ALBUM_API_PORT
from .routes.album import AlbumApiRoutes, parse_cors_origins

log = logging.getLogger("cards.album_server")


class AlbumWebServer:
    def __init__(self, db, link_secret: str, site_base_url: str) -> None:
        self._server = LocalWebServer(ALBUM_API_HOST, ALBUM_API_PORT)
        cors = parse_cors_origins(site_base_url)
        AlbumApiRoutes(db, link_secret, cors).register(self._server.app)

    async def start(self) -> None:
        await self._server.start()
        log.info(
            "Album API: http://%s:%d/api/v1/album",
            ALBUM_API_HOST,
            ALBUM_API_PORT,
        )

    async def stop(self) -> None:
        await self._server.stop()

    @property
    def local_base_url(self) -> str:
        return f"http://{ALBUM_API_HOST}:{ALBUM_API_PORT}"
