"""Точка входа: song-request + princess-бот для OBS и чата GoodGame.

Запуск (PowerShell):
    python main.py

Логи: консоль + logs/bot.log (ротация по размеру).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from bot.app import StreamBot
from config import Config

# Единый файл для разбора инцидентов: ~5 МБ × 5 файлов ≈ до 25 МБ.
_LOG_DIR = Path(__file__).resolve().parent / "logs"
_LOG_FILE = _LOG_DIR / "bot.log"
_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 5

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

_ANSI_RESET = "\033[0m"
_ANSI_RED = "\033[91m"
_ANSI_BOLD_RED = "\033[1m\033[91m"


class _ColorConsoleFormatter(logging.Formatter):
    """WARNING/ERROR/CRITICAL в CLI — красным (файл остаётся без ANSI)."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if record.levelno >= logging.ERROR:
            return f"{_ANSI_BOLD_RED}{text}{_ANSI_RESET}"
        if record.levelno >= logging.WARNING:
            return f"{_ANSI_RED}{text}{_ANSI_RESET}"
        return text


def setup_logging() -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Windows Terminal / современный conhost: включить ANSI, если доступно.
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-12)  # STD_ERROR_HANDLE
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL
        except Exception:
            pass

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Не дублировать handlers при повторном вызове (тесты / reload).
    if root.handlers:
        return

    file_formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATEFMT)
    console_formatter = _ColorConsoleFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(console_formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)
    root.addHandler(file_handler)

    # aiohttp.access шумит на каждый GET статики — приглушим.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

    logging.getLogger("main").info(
        "Логи пишутся в %s (ротация %d МБ × %d)",
        _LOG_FILE,
        _LOG_MAX_BYTES // (1024 * 1024),
        _LOG_BACKUP_COUNT,
    )


async def main() -> None:
    setup_logging()
    cfg = Config.load()

    if not cfg.gg_channel_id:
        logging.getLogger("main").warning(
            "GG_CHANNEL_ID не задан в .env — бот не сможет присоединиться к каналу."
        )

    bot = StreamBot(cfg)
    try:
        await bot.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        # Гарантированно в файл, даже если упали до/вне bot.run
        logging.getLogger("main").exception("Фатальная ошибка, бот остановлен")
        raise
