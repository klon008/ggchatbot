"""Чтение лора карт из кэша сайта (card-assets-repo)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# bot/cards/card_stories.py → parents[2] = корень проекта
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
# После sync-card-assets.ps1 / update.cmd: sparse git pull сюда
_CARD_DETAILS_PATH = (
    _PROJECT_ROOT
    / "data"
    / "card-assets-repo"
    / "src"
    / "app"
    / "cardDetails.json"
)

STORIES_SOURCE_REL = "data/card-assets-repo/src/app/cardDetails.json"


def card_details_path() -> Path:
    return _CARD_DETAILS_PATH


def load_card_stories() -> dict[str, str]:
    """slug → story. Пустой dict, если файла нет или он битый."""
    path = _CARD_DETAILS_PATH
    if not path.is_file():
        log.debug("cardDetails.json не найден: %s", path)
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        log.warning("Не удалось прочитать %s: %s", path, exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    stories = raw.get("stories")
    if not isinstance(stories, dict):
        return {}
    out: dict[str, str] = {}
    for key, val in stories.items():
        if isinstance(key, str) and isinstance(val, str) and val.strip():
            out[key.strip()] = val.strip()
    return out
