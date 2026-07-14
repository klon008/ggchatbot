"""Обработчик команд !бустер / !бустер инфо и !альбом."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from bot.db import cards as cards_db
from bot.goodgame import ChatMessage

from .album_token import build_album_url
from .draws import (
    OpenResult,
    format_open_start,
    format_open_summary,
    opening_to_ws_payload,
    open_booster,
)

if TYPE_CHECKING:
    from bot.cards.clo_tunnel import CloTunnel
    from bot.db import Database
    from bot.economy.points import PointsStore
    from bot.web.routes.player import PlayerRoutes

log = logging.getLogger("cards.handler")

ReplyFn = Callable[[str], Awaitable[None]]

# Таймаут ожидания OBS: N * 4.2s + 5s
_CARD_ANIM_SEC = 4.2
_ANIM_BASE_SEC = 5.0
_NO_CLIENTS_DELAY_SEC = 0.05


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
        self._player: Optional["PlayerRoutes"] = None
        self._present_lock = asyncio.Lock()
        self._pending_opens: dict[str, asyncio.Future[bool]] = {}

    def bind_points(self, points: "PointsStore") -> None:
        self._points = points

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_obs(self, player: "PlayerRoutes") -> None:
        self._player = player
        player.add_status_handler(self._on_obs_status)

    async def _on_obs_status(self, data: dict[str, Any]) -> None:
        if data.get("status") != "booster_done":
            return
        opening_id = data.get("openingId")
        if not isinstance(opening_id, str):
            return
        fut = self._pending_opens.get(opening_id)
        if fut is not None and not fut.done():
            fut.set_result(True)

    async def handle_message(self, msg: ChatMessage) -> bool:
        text = msg.text.strip()
        if not text.startswith("!"):
            return False
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip().lower() if len(parts) > 1 else ""

        if cmd not in ("!бустер", "!альбом"):
            return False

        meta = await cards_db.get_cards_meta(self._db)
        if not meta.get("enabled", True):
            await self._say(f"{msg.user_name}, модуль карт временно отключён.")
            return True

        if cmd == "!бустер":
            if arg == "инфо":
                await self._cmd_booster_info(msg)
            elif arg == "":
                await self._cmd_booster_buy(msg)
            else:
                await self._say(
                    f"{msg.user_name}, команды: !бустер · !бустер инфо"
                )
            return True
        await self._cmd_album(msg)
        return True

    async def _cmd_booster_buy(self, msg: ChatMessage) -> None:
        """!бустер — открыть активный тираж + OBS-презентация."""
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
            await self._say(f"{msg.user_name}, {err}")
            return
        assert result is not None
        await self._present_opening(msg.user_name, result)

    async def _present_opening(self, user_name: str, result: OpenResult) -> None:
        """FIFO: шаг 1 → WS анимация → шаг 2."""
        async with self._present_lock:
            opening_id = str(uuid.uuid4())
            await self._say(format_open_start(user_name, result))

            meta = await cards_db.get_cards_meta(self._db)
            speed = float(meta.get("anim_speed") or 1.0)
            if speed < cards_db.ANIM_SPEED_MIN:
                speed = cards_db.ANIM_SPEED_MIN
            elif speed > cards_db.ANIM_SPEED_MAX:
                speed = cards_db.ANIM_SPEED_MAX

            has_clients = bool(self._player and self._player.has_booster_clients)
            fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
            self._pending_opens[opening_id] = fut
            try:
                if has_clients and self._player is not None:
                    await self._player.broadcast(
                        opening_to_ws_payload(
                            opening_id, user_name, result, anim_speed=speed
                        )
                    )
                    timeout = (
                        len(result.rolls) * _CARD_ANIM_SEC + _ANIM_BASE_SEC
                    ) / speed
                    timeout = max(3.0, timeout)
                    try:
                        await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
                    except asyncio.TimeoutError:
                        log.warning(
                            "OBS booster_done timeout openingId=%s (N=%d speed=%.2f)",
                            opening_id,
                            len(result.rolls),
                            speed,
                        )
                else:
                    await asyncio.sleep(_NO_CLIENTS_DELAY_SEC)
            finally:
                self._pending_opens.pop(opening_id, None)

            await self._say(format_open_summary(user_name, result))

    async def _cmd_booster_info(self, msg: ChatMessage) -> None:
        """!бустер инфо — активный тираж, пул, цена и promo."""
        draw = await cards_db.get_active_draw(db=self._db)
        if draw is None:
            await self._say(f"{msg.user_name}, сейчас активного тиража нет.")
            return
        pool_size = len(
            await cards_db.list_booster_pool_ids(self._db, draw.booster_id)
        )
        promo = await cards_db.get_booster_promo_url(self._db, draw.booster_id)
        text = (
            f"{msg.user_name}, Сейчас активен «{draw.booster_name}» ({draw.name}): "
            f"{draw.cards_per_open} карт из пула {pool_size}, "
            f"цена - {draw.cost_points} принцесс."
        )
        if promo:
            text = f"{text} {promo}"
        await self._say(text)

    async def _cmd_album(self, msg: ChatMessage) -> None:
        if not self._link_secret:
            await self._say(f"{msg.user_name}, альбом пока не настроен (нет ALBUM_LINK_SECRET).")
            return

        api_url = self._clo.public_url
        if not api_url:
            await self._say(
                f"{msg.user_name}, альбом доступен на стриме (туннель не поднят)."
            )
            return

        series = await cards_db.count_series_progress(self._db, msg.user_id)
        collection = await cards_db.count_collection(self._db, msg.user_id)

        progress_parts = []
        if series:
            s = series[0]
            progress_parts.append(f"{s['owned']}/{s['total']}")
        progress_parts.append(
            f"коллекция {collection['owned']}/{collection['total']}"
        )
        progress = " · ".join(progress_parts)

        url = build_album_url(
            site_base_url=self._site_base_url,
            link_secret=self._link_secret,
            nick=msg.user_name,
            api_base_url=api_url,
        )
        await self._say(f"{msg.user_name}, альбом · {progress}\n{url}")

    async def _say(self, text: str) -> None:
        if self._reply is None:
            log.debug("Cards (no reply): %s", text)
            return
        await self._reply(text)
