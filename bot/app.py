"""Оркестратор: song-request + princess-экономика в одном GG-чате."""
from __future__ import annotations

import logging

from bot.db import Database
from config import Config

from .goodgame import GoodGameClient
from .princess import PrincessHandler
from .song_request import SongRequestHandler

log = logging.getLogger("app")


class StreamBot:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.db = Database()
        self.princess = PrincessHandler(
            db=self.db,
            admin_user_id=cfg.gg_admin_user_id,
            bot_user_id=cfg.gg_user_id,
        )
        self.sr = SongRequestHandler(cfg, db=self.db)
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
        self.princess.bind_viewers_fetch(self.gg.get_users_list)
        self.princess.bind_reply(self._princess_reply)
        self.sr.bind_reply(self._reply)
        await self.princess.start()
        self.sr.bind_points(self.princess.points)
        await self.gg.run()

    async def close(self) -> None:
        await self.princess.close()
        await self.sr.close()
        await self.gg.close()
        await self.db.close()

    async def _on_chat_message(self, msg) -> None:
        if await self.princess.handle_message(msg):
            return
        await self.sr.handle_message(msg)

    async def _princess_reply(self, user_name: str, text: str) -> None:
        await self._reply(f"{user_name}, {text}")

    async def _reply(self, text: str) -> None:
        try:
            await self.gg.send_message(text)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось отправить сообщение в чат.")

    # --- совместимость для smoke_test и старых импортов ----------------
    @property
    def queue(self):
        return self.sr.queue

    @property
    def obs(self):
        return self.sr.obs

    async def _advance(self, expected_token, skip_reason=None):
        await self.sr.advance(expected_token, skip_reason)

    @property
    def _watchdog(self):
        return self.sr._watchdog


SongRequestBot = StreamBot
