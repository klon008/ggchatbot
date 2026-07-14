"""Обработчик команд !бустер и !альбом."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

from bot.db import cards as cards_db
from bot.goodgame import ChatMessage

from .album_token import build_album_url
from .draws import format_open_chat, open_booster

if TYPE_CHECKING:
    from bot.cards.clo_tunnel import CloTunnel
    from bot.db import Database
    from bot.economy.points import PointsStore

log = logging.getLogger("cards.handler")

ReplyFn = Callable[[str], Awaitable[None]]


class CardsHandler:
    def __init__(
        self,
        db: "Database",
        *,
        link_secret: str,
        site_base_url: str,
        clo: "CloTunnel",
    ) -> None:
        self._db = db
        self._link_secret = link_secret
        self._site_base_url = site_base_url
        self._clo = clo
        self._points: Optional["PointsStore"] = None
        self._reply: Optional[ReplyFn] = None

    def bind_points(self, points: "PointsStore") -> None:
        self._points = points

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    async def handle_message(self, msg: ChatMessage) -> bool:
        text = msg.text.strip()
        if not text.startswith("!"):
            return False
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip().lower() if len(parts) > 1 else ""

        if cmd == "!бустер":
            if arg == "инфо":
                await self._cmd_booster_info(msg)
            else:
                await self._cmd_booster(msg)
            return True
        if cmd == "!альбом":
            await self._cmd_album(msg)
            return True
        return False

    async def _cmd_booster(self, msg: ChatMessage) -> None:
        if self._points is None:
            await self._say("Модуль карт не настроен.")
            return
        result, err = await open_booster(
            self._db,
            self._points,
            user_id=msg.user_id,
            user_name=msg.user_name,
        )
        if err:
            await self._say(f"@{msg.user_name}, {err}")
            return
        assert result is not None
        await self._say(f"@{msg.user_name} · {format_open_chat(result)}")

    async def _cmd_booster_info(self, msg: ChatMessage) -> None:
        draw = await cards_db.get_active_draw(db=self._db)
        if draw is None:
            await self._say(f"@{msg.user_name}, активного тиража нет.")
            return
        promo = await cards_db.get_booster_promo_url(self._db, draw.booster_id)
        text = (
            f"@{msg.user_name} · {draw.name} · Бустер «{draw.booster_name}» · "
            f"{draw.cost_points} баллов · {draw.cards_per_open} карт за открытие."
        )
        if promo:
            text += f" Promo (OBS): {promo}"
        await self._say(text)

    async def _cmd_album(self, msg: ChatMessage) -> None:
        if not self._link_secret:
            await self._say(f"@{msg.user_name}, альбом пока не настроен (нет ALBUM_LINK_SECRET).")
            return

        api_url = self._clo.public_url
        if not api_url:
            await self._say(
                f"@{msg.user_name}, альбом доступен на стриме (туннель не поднят)."
            )
            return

        series = await cards_db.count_series_progress(self._db, msg.user_id)
        collection = await cards_db.count_collection(self._db, msg.user_id)

        progress_parts = []
        if series:
            s = series[0]
            progress_parts.append(f"серия «{s['name']}»: {s['owned']} из {s['total']}")
        progress_parts.append(
            f"Коллекция: {collection['owned']} из {collection['total']}"
        )
        progress = " · ".join(progress_parts)

        url = build_album_url(
            site_base_url=self._site_base_url,
            link_secret=self._link_secret,
            nick=msg.user_name,
            api_base_url=api_url,
        )
        await self._say(
            f"@{msg.user_name} · Альбом · {progress}\n{url}"
        )

    async def _say(self, text: str) -> None:
        if self._reply is None:
            log.debug("Cards (no reply): %s", text)
            return
        await self._reply(text)
