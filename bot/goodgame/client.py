"""WebSocket-клиент чата GoodGame (протокол v2).

Док: https://github.com/GoodGame/API/blob/master/Chat/protocol2.md
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable, Deque, Optional, Set

import aiohttp
import websockets

log = logging.getLogger("goodgame")

WS_URL = "wss://chat-1.goodgame.ru/chat2/"
CHATLOGIN_URL = "https://goodgame.ru/ajax/chatlogin"
USERS_LIST_TIMEOUT_SEC = 10.0
SEND_MESSAGE_ECHO_TIMEOUT_SEC = 5.0
AUTH_TIMEOUT_SEC = 8.0
JOIN_TIMEOUT_SEC = 8.0
CHATLOGIN_RETRIES = 3
CHATLOGIN_RETRY_DELAY_SEC = 1.5
# Сколько незавершённых обработчиков сообщений считать подозрительным backlog.
DISPATCH_BACKLOG_WARN = 25

RIGHTS_STREAM_MODER = 10


@dataclass
class ChatMessage:
    channel_id: str
    user_id: str
    user_name: str
    user_rights: int
    text: str

    @property
    def is_moderator(self) -> bool:
        return self.user_rights >= RIGHTS_STREAM_MODER


MessageHandler = Callable[[ChatMessage], Awaitable[None]]


def _cli_error(msg: str) -> None:
    """Яркое предупреждение в консоль (файл лога — через log.*)."""
    red = "\033[91m"
    bold = "\033[1m"
    reset = "\033[0m"
    print(f"{bold}{red}⚠ {msg}{reset}", flush=True)


class GoodGameClient:
    def __init__(
        self,
        login: str,
        password: str,
        channel_id: str,
        on_message: MessageHandler,
        user_id: str = "",
    ) -> None:
        self.login = login
        self.password = password
        self.channel_id = str(channel_id)
        self.user_id = str(user_id)
        self.token: str = ""
        self._on_message = on_message
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._stop = False
        self._authenticated = False
        self._joined = False
        self._banned = False
        self._users_list_lock = asyncio.Lock()
        self._users_list_future: Optional[asyncio.Future] = None
        self._auth_future: Optional[asyncio.Future] = None
        self._join_future: Optional[asyncio.Future] = None
        self._pending_send_futures: Deque[asyncio.Future] = deque()
        self._dispatch_tasks: Set[asyncio.Task] = set()

    @property
    def can_send(self) -> bool:
        return (
            bool(self.token)
            and self._authenticated
            and self._joined
            and not self._banned
            and self._ws is not None
        )

    async def _fetch_token(self) -> bool:
        """Обновить token через chatlogin. При ошибке старый token не затираем."""
        if not self.login or not self.password:
            log.warning("GG_LOGIN/GG_PASSWORD не заданы — бот работает как гость (readonly).")
            return False
        try:
            async with aiohttp.ClientSession() as session:
                form = aiohttp.FormData()
                form.add_field("login", self.login)
                form.add_field("password", self.password)
                async with session.post(CHATLOGIN_URL, data=form) as resp:
                    raw = await resp.text()
                    if resp.status != 200:
                        log.error(
                            "Ошибка chatlogin: HTTP %s, body=%r",
                            resp.status,
                            raw[:200],
                        )
                        return False
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        log.error(
                            "Ошибка chatlogin: не JSON (%s), body=%r",
                            exc,
                            raw[:200],
                        )
                        return False
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.error("Ошибка chatlogin: %s", exc)
            return False

        if not data.get("result"):
            log.error("chatlogin отклонён: %s", data.get("response"))
            return False

        new_token = str(data.get("token") or "")
        if not new_token:
            log.error("chatlogin без token: %s", data.get("response"))
            return False

        self.user_id = str(data.get("user_id") or self.user_id)
        self.token = new_token
        log.info(
            "Авторизация в GG успешна: user_id=%s (%s)",
            self.user_id,
            data.get("response"),
        )
        return True

    async def _fetch_token_with_retries(self) -> bool:
        for attempt in range(1, CHATLOGIN_RETRIES + 1):
            if await self._fetch_token():
                return True
            if attempt < CHATLOGIN_RETRIES:
                log.warning(
                    "chatlogin не удался (%d/%d), повтор через %.1fс…",
                    attempt,
                    CHATLOGIN_RETRIES,
                    CHATLOGIN_RETRY_DELAY_SEC,
                )
                await asyncio.sleep(CHATLOGIN_RETRY_DELAY_SEC)
        if self.token:
            log.warning(
                "chatlogin не обновил token — используем предыдущий (может быть просрочен)."
            )
            return True
        return False

    async def run(self) -> None:
        await self._fetch_token_with_retries()
        backoff = 1
        while not self._stop:
            try:
                await self._connect_and_listen()
                backoff = 1
            except (websockets.WebSocketException, OSError) as exc:
                log.warning(
                    "Соединение с GG прервано: %s. Reconnect через %dс.", exc, backoff
                )
            except Exception:  # noqa: BLE001
                log.exception(
                    "Непредвиденная ошибка GG-клиента. Reconnect через %dс.", backoff
                )
            if self._stop:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            await self._fetch_token_with_retries()

    async def _connect_and_listen(self) -> None:
        self._authenticated = False
        self._joined = False
        self._banned = False
        try:
            async with websockets.connect(
                WS_URL, ping_interval=20, ping_timeout=20
            ) as ws:
                self._ws = ws
                log.info("Подключение к чату GG установлено.")

                # Читаем сокет параллельно с auth/join — иначе wait_for никогда
                # не получит success_auth/success_join (сообщения лежат в буфере).
                reader = asyncio.create_task(
                    self._read_loop(ws), name="gg-ws-reader"
                )
                try:
                    if self.token and self.user_id:
                        ok = await self._authenticate()
                        if not ok:
                            _cli_error(
                                "GoodGame: auth не прошёл после reconnect. "
                                "Бот в режиме readonly (команды видит, в чат писать не может). "
                                "Проверьте GG_LOGIN/GG_PASSWORD или дождитесь восстановления GG."
                            )
                            log.error(
                                "GG auth failed — работаем без права отправки сообщений"
                            )
                    elif self.login and self.password:
                        _cli_error(
                            "GoodGame: нет token (chatlogin не удался). "
                            "Бот подключён как гость — читать может, писать в чат нет."
                        )
                        log.error("GG без token — guest/readonly join")
                    else:
                        log.warning("GG guest mode (логин не задан)")

                    joined = await self._join_channel()
                    if not joined:
                        _cli_error(
                            f"GoodGame: не получили success_join для канала {self.channel_id}. "
                            "Команды не будут приходить. Проверьте GG_CHANNEL_ID."
                        )
                        log.error(
                            "GG join failed — канал %s, сообщения чата недоступны",
                            self.channel_id,
                        )
                    else:
                        log.info(
                            "В канале %s (send=%s).",
                            self.channel_id,
                            "ok" if self.can_send else "readonly",
                        )

                    # Держим соединение, пока reader не завершится (disconnect/ошибка).
                    await reader
                finally:
                    if not reader.done():
                        reader.cancel()
                        try:
                            await reader
                        except asyncio.CancelledError:
                            pass
        finally:
            self._authenticated = False
            self._joined = False
            self._banned = False
            self._cancel_auth_waiter()
            self._cancel_join_waiter()
            self._cancel_users_list_waiter()
            self._fail_pending_sends(ConnectionError("WebSocket отключён"))
            self._ws = None

    async def _read_loop(self, ws) -> None:
        async for raw in ws:
            await self._handle_raw(raw)

    async def _authenticate(self) -> bool:
        """Отправить auth и дождаться success_auth."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._auth_future = fut
        try:
            await self._send(
                {
                    "type": "auth",
                    "data": {
                        "user_id": int(self.user_id),
                        "token": self.token,
                    },
                }
            )
            await asyncio.wait_for(asyncio.shield(fut), timeout=AUTH_TIMEOUT_SEC)
            return True
        except asyncio.TimeoutError:
            log.error("Таймаут ожидания success_auth (%.0fс)", AUTH_TIMEOUT_SEC)
            return False
        except Exception:  # noqa: BLE001
            log.exception("Ошибка при auth")
            return False
        finally:
            if self._auth_future is fut:
                self._auth_future = None
            if not fut.done():
                fut.cancel()

    async def _join_channel(self) -> bool:
        """Отправить join и дождаться success_join."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._join_future = fut
        try:
            await self._send(
                {
                    "type": "join",
                    "data": {"channel_id": self.channel_id, "hidden": 0},
                }
            )
            log.info("join отправлен в канал %s, ждём success_join…", self.channel_id)
            await asyncio.wait_for(asyncio.shield(fut), timeout=JOIN_TIMEOUT_SEC)
            return True
        except asyncio.TimeoutError:
            log.error("Таймаут ожидания success_join (%.0fс)", JOIN_TIMEOUT_SEC)
            return False
        except Exception:  # noqa: BLE001
            log.exception("Ошибка при join")
            return False
        finally:
            if self._join_future is fut:
                self._join_future = None
            if not fut.done():
                fut.cancel()

    async def _handle_raw(self, raw: str) -> None:
        try:
            packet = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("GG: невалидный JSON (%d байт)", len(raw))
            return
        ptype = packet.get("type")
        data = packet.get("data", {}) or {}

        if ptype == "success_auth":
            self.user_id = str(data.get("user_id") or self.user_id)
            self._authenticated = True
            log.info("auth OK: %s", data.get("user_name"))
            if self._auth_future is not None and not self._auth_future.done():
                self._auth_future.set_result(True)
        elif ptype == "success_join":
            ch = str(data.get("channel_id", self.channel_id))
            banned = bool(data.get("is_banned"))
            smile_only = bool(data.get("smile_only_mode"))
            # Забаненный клиент не считается joined: send/get_users_list должны отказать.
            self._banned = banned
            self._joined = not banned
            log.info(
                "success_join channel=%s name=%r banned=%s smile_only=%s rights=%s",
                ch,
                data.get("channel_name") or data.get("channel_key") or "",
                banned,
                smile_only,
                data.get("access_rights"),
            )
            if banned:
                _cli_error(
                    "GoodGame: бот забанен в канале — писать в чат нельзя."
                )
                log.error("GG is_banned=true в канале %s", ch)
                if self._join_future is not None and not self._join_future.done():
                    self._join_future.set_exception(
                        ConnectionError(f"GG banned in channel {ch}")
                    )
            else:
                if smile_only:
                    log.warning(
                        "В канале smile_only_mode — текстовые ответы могут резаться GG"
                    )
                if self._join_future is not None and not self._join_future.done():
                    self._join_future.set_result(True)
        elif ptype == "unjoin":
            ch = str(data.get("channel_id", ""))
            self._joined = False
            self._banned = False
            log.warning("GG unjoin channel=%s — сообщения канала больше не приходят", ch)
        elif ptype == "error":
            err = data.get("errorMsg") or data.get("message") or data
            log.warning("GG error: %s", err)
            # Невалидный token / права — auth не состоится
            err_l = str(err).lower()
            if self._auth_future is not None and not self._auth_future.done():
                if "auth" in err_l or "token" in err_l or "логин" in err_l:
                    self._auth_future.set_exception(
                        ConnectionError(f"GG auth error: {err}")
                    )
            if self._join_future is not None and not self._join_future.done():
                if (
                    "канал" in err_l
                    or "channel" in err_l
                    or "join" in err_l
                    or "не найден" in err_l
                ):
                    self._join_future.set_exception(
                        ConnectionError(f"GG join error: {err}")
                    )
        elif ptype == "users_list":
            self._resolve_users_list(data.get("users") or [])
        elif ptype == "message":
            await self._handle_message(data)

    async def _handle_message(self, data: dict) -> None:
        user_id = str(data.get("user_id", "0"))
        if self.user_id and user_id == self.user_id:
            message_id = data.get("message_id")
            self._resolve_own_send(str(message_id) if message_id is not None else "")
            return

        msg = ChatMessage(
            channel_id=str(data.get("channel_id", self.channel_id)),
            user_id=user_id,
            user_name=str(data.get("user_name", "")),
            user_rights=int(data.get("user_rights", 0) or 0),
            text=str(data.get("text", "")),
        )
        text = msg.text.strip()
        if text.startswith("!"):
            log.info("GG !cmd from=%s text=%r", msg.user_name, text[:80])
            backlog = len(self._dispatch_tasks)
            if backlog >= DISPATCH_BACKLOG_WARN:
                log.warning(
                    "Обработчиков сообщений в полёте: %d — возможен зависший DB/handler",
                    backlog,
                )
        # Не блокируем WS-reader: иначе send_message(wait echo) из handler — deadlock.
        task = asyncio.create_task(self._dispatch_message(msg), name="gg-on-message")
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._dispatch_tasks.discard)

    async def _dispatch_message(self, msg: ChatMessage) -> None:
        try:
            await self._on_message(msg)
        except Exception:  # noqa: BLE001
            log.exception("Ошибка обработчика сообщения GG")

    def _resolve_own_send(self, message_id: str) -> None:
        while self._pending_send_futures:
            fut = self._pending_send_futures.popleft()
            if fut.done():
                continue
            fut.set_result(message_id or None)
            return

    def _fail_pending_sends(self, exc: BaseException) -> None:
        while self._pending_send_futures:
            fut = self._pending_send_futures.popleft()
            if not fut.done():
                fut.set_exception(exc)

    async def _send(self, obj: dict) -> None:
        if self._ws is None:
            return
        await self._ws.send(json.dumps(obj, ensure_ascii=False))

    def _resolve_users_list(self, users: list) -> None:
        if self._users_list_future is not None and not self._users_list_future.done():
            self._users_list_future.set_result(users)

    def _cancel_users_list_waiter(self) -> None:
        if self._users_list_future is not None and not self._users_list_future.done():
            self._users_list_future.set_exception(ConnectionError("WebSocket отключён"))
        self._users_list_future = None

    def _cancel_auth_waiter(self) -> None:
        if self._auth_future is not None and not self._auth_future.done():
            self._auth_future.set_exception(ConnectionError("WebSocket отключён"))
        self._auth_future = None

    def _cancel_join_waiter(self) -> None:
        if self._join_future is not None and not self._join_future.done():
            self._join_future.set_exception(ConnectionError("WebSocket отключён"))
        self._join_future = None

    async def get_users_list(self) -> list[dict]:
        """Запросить список авторизованных зрителей в чате канала (get_users_list2)."""
        if self._ws is None:
            raise ConnectionError("WebSocket не подключён")
        if self._banned:
            raise ConnectionError("Бот забанен в канале")
        if not self._joined:
            raise ConnectionError("Ещё не в канале (нет success_join)")

        async with self._users_list_lock:
            if self._users_list_future is not None and not self._users_list_future.done():
                raise RuntimeError("get_users_list уже выполняется")

            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self._users_list_future = fut
            try:
                await self._send(
                    {
                        "type": "get_users_list2",
                        "data": {"channel_id": self.channel_id},
                    }
                )
                return await asyncio.wait_for(fut, timeout=USERS_LIST_TIMEOUT_SEC)
            finally:
                if self._users_list_future is fut:
                    self._users_list_future = None

    async def send_message(self, text: str) -> Optional[str]:
        """Отправить сообщение и вернуть message_id из echo (или None)."""
        if not self.login or not self.password:
            log.warning("Пропуск ответа в чат (гость без логина): %s", text[:120])
            return None
        if not self.token:
            log.error(
                "Пропуск send_message: нет token (chatlogin не удался). Текст: %s",
                text[:120],
            )
            return None
        if not self._authenticated:
            log.error(
                "Пропуск send_message: нет success_auth (readonly после reconnect). "
                "Текст: %s",
                text[:120],
            )
            return None
        if self._banned:
            log.error(
                "Пропуск send_message: бот забанен в канале. Текст: %s",
                text[:120],
            )
            return None
        if not self._joined:
            log.error(
                "Пропуск send_message: нет success_join (не в канале). Текст: %s",
                text[:120],
            )
            return None
        if self._ws is None:
            log.warning("Пропуск send_message: WebSocket не подключён")
            return None

        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_send_futures.append(fut)
        try:
            await self._send(
                {
                    "type": "send_message",
                    "data": {
                        "channel_id": self.channel_id,
                        "text": text,
                        "mobile": 0,
                    },
                }
            )
            # shield: wait_for не должен cancel'ить fut до remove из очереди
            message_id = await asyncio.wait_for(
                asyncio.shield(fut), timeout=SEND_MESSAGE_ECHO_TIMEOUT_SEC
            )
            return str(message_id) if message_id else None
        except asyncio.TimeoutError:
            log.warning("Таймаут ожидания message_id для send_message")
            return None
        except ConnectionError:
            log.warning("Соединение закрыто до получения message_id")
            return None
        finally:
            try:
                self._pending_send_futures.remove(fut)
            except ValueError:
                pass
            if not fut.done():
                fut.cancel()

    async def remove_message(self, message_id: str) -> None:
        """Удалить сообщение по id (нужны права stream_moder+)."""
        if not message_id or not self.can_send:
            return
        await self._send(
            {
                "type": "remove_message",
                "data": {
                    "channel_id": self.channel_id,
                    "message_id": str(message_id),
                },
            }
        )

    async def close(self) -> None:
        self._stop = True
        if self._ws is not None:
            await self._ws.close()
