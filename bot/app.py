"""Оркестратор: song-request + princess-экономика в одном GG-чате."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from bot.cards import CardsHandler
from bot.cards.album_server import AlbumWebServer
from bot.cards.clo_tunnel import CloTunnel, CloTunnelError
from bot.commands import HELP_COMMAND, format_help
from bot.db import Database
from bot.web import LocalWebServer
from bot.cards.routes.admin_api import CardsAdminRoutes
from bot.web.routes.admin import AdminRoutes
from bot.web.routes.docs import DocsRoutes
from config import Config

from .goodgame import GoodGameClient
from .princess import PrincessHandler
from .races import RacesHandler
from .roulette import RouletteHandler
from .song_request import SongRequestHandler

log = logging.getLogger("app")


class StreamBot:
    def __init__(self, cfg: Config, db_path: Optional[Path] = None) -> None:
        self.cfg = cfg
        self.db = Database(db_path)
        self.web = LocalWebServer(cfg.obs_host, cfg.obs_port)
        self.princess = PrincessHandler(
            db=self.db,
            admin_user_id=cfg.gg_admin_user_id,
            bot_user_id=cfg.gg_user_id,
        )
        self.sr = SongRequestHandler(cfg, db=self.db, web=self.web)
        self.roulette = RouletteHandler(
            db=self.db,
            admin_user_id=cfg.gg_admin_user_id,
        )
        self.races = RacesHandler(
            db=self.db,
            admin_user_id=cfg.gg_admin_user_id,
        )
        self.album_web = AlbumWebServer(
            self.db,
            cfg.album_link_secret,
            cfg.site_base_url,
        )
        self.clo = CloTunnel(
            cfg.clo_exe_path,
            fallback_url=cfg.clo_public_url,
            token=cfg.clo_token,
        )
        self.cards = CardsHandler(
            self.db,
            link_secret=cfg.album_link_secret,
            site_base_url=cfg.site_base_url,
            clo=self.clo,
        )
        DocsRoutes().register(self.web.app)
        self.admin = AdminRoutes(self.db, self.sr.queue, self.sr, self.roulette, self.races)
        self.admin.register(self.web.app)
        CardsAdminRoutes(self.db).register(self.web.app)
        self.gg = GoodGameClient(
            login=cfg.gg_login,
            password=cfg.gg_password,
            channel_id=cfg.gg_channel_id,
            on_message=self._on_chat_message,
            user_id=cfg.gg_user_id,
        )

    async def run(self) -> None:
        await self.db.open()
        await self.sr.start()
        await self.web.start()
        await self.album_web.start()
        try:
            await self.clo.start()
        except CloTunnelError:
            log.error(
                "Album CLO не поднялся — !альбом недоступен. "
                "Проверь CLO_TOKEN / CLO_EXE_PATH или задай CLO_PUBLIC_URL для тестов."
            )
            raise
        log.info("OBS-плеер: http://%s:%d/player.html", self.cfg.obs_host, self.cfg.obs_port)
        log.info("Рулетка OBS: http://%s:%d/roulette.html", self.cfg.obs_host, self.cfg.obs_port)
        log.info("Скачки OBS: http://%s:%d/races.html", self.cfg.obs_host, self.cfg.obs_port)
        log.info("Admin-панель: http://%s:%d/admin.html", self.cfg.obs_host, self.cfg.obs_port)
        log.info("Логика команд: http://%s:%d/commands.html", self.cfg.obs_host, self.cfg.obs_port)
        self.admin.bind_user_names(
            self.gg.get_users_list,
            self.princess.points,
        )
        self.princess.bind_viewers_fetch(self.gg.get_users_list)
        self.princess.bind_reply(self._princess_reply)
        self.sr.bind_reply(self._reply)
        await self.princess.start()
        await self.roulette.start()
        await self.races.start()
        self.roulette.bind_reply(self._reply)
        self.races.bind_reply(self._reply)
        self.roulette.bind_points(self.princess.points)
        self.races.bind_points(self.princess.points)
        self.sr.bind_points(self.princess.points)
        self.cards.bind_points(self.princess.points)
        self.cards.bind_reply(self._reply)
        await self.gg.run()

    async def close(self) -> None:
        await self.princess.close()
        await self.roulette.close()
        await self.races.close()
        await self.sr.close()
        await self.clo.stop()
        await self.album_web.stop()
        await self.web.stop()
        await self.gg.close()
        await self.db.close()

    async def _on_chat_message(self, msg) -> None:
        cmd = msg.text.strip().split(maxsplit=1)[0].lower()
        if cmd == HELP_COMMAND:
            await self._reply(f"{msg.user_name}, {format_help()}")
            return
        if await self.princess.handle_message(msg):
            return
        if await self.cards.handle_message(msg):
            return
        if await self.roulette.handle_message(msg):
            return
        if await self.races.handle_message(msg):
            return
        await self.sr.handle_message(msg)

    async def _princess_reply(self, user_name: str, text: str) -> None:
        await self._reply(f"{user_name}, {text}")

    async def _reply(self, text: str) -> None:
        try:
            await self.gg.send_message(text)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось отправить сообщение в чат.")
