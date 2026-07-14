"""Загрузка конфигурации из .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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

    album_link_secret: str
    site_base_url: str
    clo_exe_path: str
    clo_token: str
    clo_public_url: str

    @classmethod
    def load(cls) -> "Config":
        root = Path(__file__).resolve().parent
        default_clo = str(root / "tools" / "clo" / "clo.exe")
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
            album_link_secret=os.getenv("ALBUM_LINK_SECRET", "").strip(),
            site_base_url=os.getenv(
                "SITE_BASE_URL",
                "https://klon008.github.io/princtascdwk",
            ).strip(),
            clo_exe_path=os.getenv("CLO_EXE_PATH", default_clo).strip() or default_clo,
            clo_token=os.getenv("CLO_TOKEN", "").strip(),
            clo_public_url=os.getenv("CLO_PUBLIC_URL", "").strip(),
        )
