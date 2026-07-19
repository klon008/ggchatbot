"""Merge pack stories into local card-assets-repo cache for admin lore."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from bot.cards.card_stories import card_details_path

LogFn = Callable[[str], None]


def merge_stories_cache(stories: dict[str, str], log: LogFn) -> Path:
    path = card_details_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {"v": 1, "stories": {}}
    else:
        raw = {"v": 1, "stories": {}}
    if not isinstance(raw, dict):
        raw = {"v": 1, "stories": {}}
    bucket = raw.setdefault("stories", {})
    if not isinstance(bucket, dict):
        bucket = {}
        raw["stories"] = bucket
    for cid, text in stories.items():
        bucket[cid] = text
    path.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    log(f"Лор → {path.as_posix()} ({len(stories)} stories)")
    return path
