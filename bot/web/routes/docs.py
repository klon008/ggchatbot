"""Маршруты страницы документации команд бота."""
from __future__ import annotations

from aiohttp import web

from bot.web.static import serve_obs_file


class DocsRoutes:
    def register(self, app: web.Application) -> None:
        app.add_routes(
            [
                web.get("/commands.html", self._handle_commands),
                web.get("/mermaid.min.js", self._handle_mermaid_js),
            ]
        )

    async def _handle_commands(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("commands.html", "text/html; charset=utf-8")

    async def _handle_mermaid_js(self, request: web.Request) -> web.StreamResponse:
        return await serve_obs_file("mermaid.min.js", "application/javascript; charset=utf-8")
