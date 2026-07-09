"""Точка входа: song-request + princess-бот для OBS и чата GoodGame.

Запуск (PowerShell):
    python main.py
"""
from __future__ import annotations

import asyncio
import logging

from bot.app import StreamBot
from config import Config


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # aiohttp.access шумит на каждый GET статики — приглушим.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


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
