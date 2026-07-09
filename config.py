"""Загрузка конфигурации из .env."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Config:
    gg_login: str
    gg_password: str
    gg_user_id: str
    gg_channel_id: str
    gg_channel_key: str
    gg_admin_user_id: str

    obs_host: str
    obs_port: int

    max_queue_size: int
    max_duration_sec: int
    track_watchdog_extra_sec: int
    user_cooldown_sec: int

    youtube_api_key: str

    @classmethod
    def load(cls) -> "Config":
        return cls(
            gg_login=os.getenv("GG_LOGIN", "").strip(),
            gg_password=os.getenv("GG_PASSWORD", "").strip(),
            gg_user_id=os.getenv("GG_USER_ID", "").strip(),
            gg_channel_id=os.getenv("GG_CHANNEL_ID", "").strip(),
            gg_channel_key=os.getenv("GG_CHANNEL_KEY", "").strip(),
            gg_admin_user_id=os.getenv("GG_ADMIN_USER_ID", "").strip(),
            obs_host=os.getenv("OBS_WS_HOST", "127.0.0.1").strip() or "127.0.0.1",
            obs_port=_get_int("OBS_WS_PORT", 8765),
            max_queue_size=_get_int("MAX_QUEUE_SIZE", 50),
            max_duration_sec=_get_int("MAX_DURATION_SEC", 300),
            track_watchdog_extra_sec=_get_int("TRACK_WATCHDOG_EXTRA_SEC", 60),
            user_cooldown_sec=_get_int("USER_COOLDOWN_SEC", 0),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY", "").strip(),
        )
