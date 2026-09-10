"""Admin API: авто-ответы и сообщения по таймеру (localhost OBS, порт 8765)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

from bot.commands import HELP_COMMAND, PUBLIC_COMMANDS
from bot.db import messaging as messaging_db
from bot.web.api import error_response, json_response, read_json

if TYPE_CHECKING:
    from bot.db import Database
    from bot.messaging.handler import MessagingHandler

MAX_COMMAND_LEN = 32
MAX_TEXT_LEN = 500
MIN_INTERVAL_SEC = 60
MAX_INTERVAL_SEC = 86400


def _parse_id(request: web.Request) -> Optional[int]:
    try:
        return int(request.match_info["item_id"])
    except (KeyError, ValueError):
        return None


def _validate_command(raw: Any) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(raw, str):
        return None, "Команда должна быть строкой"
    command = raw.strip().lower()
    if not command:
        return None, "Команда обязательна"
    if not command.startswith("!"):
        return None, "Команда должна начинаться с !"
    if len(command.split()) != 1:
        return None, "Команда — одно слово без пробелов"
    if len(command) > MAX_COMMAND_LEN:
        return None, f"Команда длиннее {MAX_COMMAND_LEN} символов"
    return command, None


def _is_reserved_command(command: str) -> bool:
    return command == HELP_COMMAND or command in PUBLIC_COMMANDS


def _validate_text(raw: Any) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(raw, str):
        return None, "Текст должен быть строкой"
    text = raw.strip()
    if not text:
        return None, "Текст обязателен"
    if len(text) > MAX_TEXT_LEN:
        return None, f"Текст длиннее {MAX_TEXT_LEN} символов"
    return text, None


def _validate_interval(raw: Any) -> tuple[Optional[int], Optional[str]]:
    try:
        interval = int(raw)
    except (TypeError, ValueError):
        return None, "Интервал должен быть числом секунд"
    if interval < MIN_INTERVAL_SEC:
        return None, f"Минимальный интервал — {MIN_INTERVAL_SEC} секунд"
    if interval > MAX_INTERVAL_SEC:
        return None, f"Максимальный интервал — {MAX_INTERVAL_SEC} секунд"
    return interval, None


class MessagingAdminRoutes:
    def __init__(self, db: "Database", messaging: "MessagingHandler") -> None:
        self._db = db
        self._messaging = messaging

    def register(self, app: web.Application) -> None:
        app.add_routes(
            [
                web.get("/api/messaging/auto-responses", self._auto_list),
                web.post("/api/messaging/auto-responses", self._auto_create),
                web.put("/api/messaging/auto-responses/{item_id}", self._auto_update),
                web.delete("/api/messaging/auto-responses/{item_id}", self._auto_delete),
                web.get("/api/messaging/timed", self._timed_list),
                web.post("/api/messaging/timed", self._timed_create),
                web.put("/api/messaging/timed/{item_id}", self._timed_update),
                web.delete("/api/messaging/timed/{item_id}", self._timed_delete),
            ]
        )

    # --- Авто-ответы ---------------------------------------------------------

    async def _auto_list(self, request: web.Request) -> web.Response:
        items = await messaging_db.list_auto_responses(self._db)
        return json_response({"items": items})

    async def _auto_create(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        command, err = _validate_command(data.get("command"))
        if err:
            return error_response(err)
        if _is_reserved_command(command):
            return error_response(f"Команда {command} уже есть у бота", status=409)
        reply, err = _validate_text(data.get("reply"))
        if err:
            return error_response(err)
        enabled = bool(data.get("enabled", True))
        if await messaging_db.get_auto_response_by_command(self._db, command):
            return error_response(f"Команда {command} уже настроена", status=409)
        item = await messaging_db.create_auto_response(
            self._db, command, reply, enabled=enabled
        )
        await self._messaging.reload()
        return json_response(item, status=201)

    async def _auto_update(self, request: web.Request) -> web.Response:
        item_id = _parse_id(request)
        if item_id is None:
            return error_response("Некорректный id")
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        kwargs: dict[str, Any] = {}
        if "command" in data:
            command, err = _validate_command(data.get("command"))
            if err:
                return error_response(err)
            if _is_reserved_command(command):
                return error_response(f"Команда {command} уже есть у бота", status=409)
            existing = await messaging_db.get_auto_response_by_command(self._db, command)
            if existing and int(existing["id"]) != item_id:
                return error_response(f"Команда {command} уже настроена", status=409)
            kwargs["command"] = command
        if "reply" in data:
            reply, err = _validate_text(data.get("reply"))
            if err:
                return error_response(err)
            kwargs["reply"] = reply
        if "enabled" in data:
            kwargs["enabled"] = bool(data.get("enabled"))
        item = await messaging_db.update_auto_response(self._db, item_id, **kwargs)
        if item is None:
            return error_response("Запись не найдена", status=404)
        await self._messaging.reload()
        return json_response(item)

    async def _auto_delete(self, request: web.Request) -> web.Response:
        item_id = _parse_id(request)
        if item_id is None:
            return error_response("Некорректный id")
        deleted = await messaging_db.delete_auto_response(self._db, item_id)
        if not deleted:
            return error_response("Запись не найдена", status=404)
        await self._messaging.reload()
        return json_response({"ok": True})

    # --- Сообщения по таймеру ------------------------------------------------

    async def _timed_list(self, request: web.Request) -> web.Response:
        items = await messaging_db.list_timed_messages(self._db)
        return json_response({"items": items})

    async def _timed_create(self, request: web.Request) -> web.Response:
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        text, err = _validate_text(data.get("text"))
        if err:
            return error_response(err)
        interval, err = _validate_interval(data.get("interval_sec"))
        if err:
            return error_response(err)
        enabled = bool(data.get("enabled", True))
        item = await messaging_db.create_timed_message(
            self._db,
            text,
            interval,
            enabled=enabled,
        )
        self._messaging.wake()
        return json_response(item, status=201)

    async def _timed_update(self, request: web.Request) -> web.Response:
        item_id = _parse_id(request)
        if item_id is None:
            return error_response("Некорректный id")
        data = await read_json(request)
        if data is None:
            return error_response("Некорректный JSON")
        current = await messaging_db.get_timed_message(self._db, item_id)
        if current is None:
            return error_response("Запись не найдена", status=404)
        kwargs: dict[str, Any] = {}
        reschedule = False
        if "text" in data:
            text, err = _validate_text(data.get("text"))
            if err:
                return error_response(err)
            kwargs["text"] = text
        if "interval_sec" in data:
            interval, err = _validate_interval(data.get("interval_sec"))
            if err:
                return error_response(err)
            kwargs["interval_sec"] = interval
            reschedule = True
        if "enabled" in data:
            enabled = bool(data.get("enabled"))
            kwargs["enabled"] = enabled
            if enabled and not current["enabled"]:
                # Повторное включение — таймер стартует заново, без досыла.
                reschedule = True
        item = await messaging_db.update_timed_message(self._db, item_id, **kwargs)
        assert item is not None
        if reschedule:
            interval = int(item["interval_sec"])
            await messaging_db.set_timed_schedule(
                self._db,
                item_id,
                next_send_at=time.time() + interval,
            )
        self._messaging.wake()
        return json_response(item)

    async def _timed_delete(self, request: web.Request) -> web.Response:
        item_id = _parse_id(request)
        if item_id is None:
            return error_response("Некорректный id")
        deleted = await messaging_db.delete_timed_message(self._db, item_id)
        if not deleted:
            return error_response("Запись не найдена", status=404)
        self._messaging.wake()
        return json_response({"ok": True})
