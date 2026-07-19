"""Выбор состава забега."""

from __future__ import annotations

import random

from bot.db.races import LineupEntry
from bot.princesses import DISNEY_PRINCESSES

from .settings import RUNNERS_COUNT

# Unicode circled digits ①…⑳ для чата (вместо «№1»)
_CIRCLED_NUMS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def format_horse_mark(n: int) -> str:
    """Номер лошади для чата: ①…⑥, иначе №N."""
    if 1 <= n <= len(_CIRCLED_NUMS):
        return _CIRCLED_NUMS[n - 1]
    return f"№{n}"


def pick_lineup(count: int = RUNNERS_COUNT) -> list[LineupEntry]:
    names = random.sample(list(DISNEY_PRINCESSES), min(count, len(DISNEY_PRINCESSES)))
    return [
        LineupEntry(horse_number=i + 1, princess_name=name)
        for i, name in enumerate(names)
    ]


def format_lineup_short(lineup: list[LineupEntry]) -> str:
    parts = [f"{format_horse_mark(e.horse_number)} {e.princess_name}" for e in lineup]
    return ", ".join(parts)
