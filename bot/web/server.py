"""Общий локальный aiohttp-сервер для OBS-плеера, админки и документации."""
from __future__ import annotations

import logging
from typing import Optional

from aiohttp import web

log = logging.getLogger("web")


class LocalWebServer:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None

    @property
    def app(self) -> web.Application:
        return self._app

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        log.info("Локальный веб-сервер запущен: http://%s:%d/", self.host, self.port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
