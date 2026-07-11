"""Игровая математика: шансы, бонусы, склонения."""
from __future__ import annotations

import random
from datetime import datetime

from .settings import (
    DAILY_BONUS_DEFAULT,
    DAILY_BONUS_MAP,
    MSK,
    PRISON_CHANCE_TIERS,
    STEAL_ALLOWED_WEEKDAYS,
    STEAL_CHANCE_ABSOLUTE_MAX,
    STEAL_CHANCE_BASE,
    STEAL_CHANCE_BEGINNER,
    STEAL_CHANCE_BEGINNER_ATTEMPTS,
    STEAL_CHANCE_INTERMEDIATE,
    STEAL_CHANCE_INTERMEDIATE_ATTEMPTS,
    STEAL_CHANCE_LINEAR_MAX,
    STEAL_CHANCE_MIN_ATTEMPTS_FOR_BONUS,
    STEAL_CHANCE_SUCCESS_LINEAR_CAP,
    STEAL_LOOT_TIERS,
)


def now_msk() -> datetime:
    return datetime.now(MSK)


def update_chance(info: dict) -> None:
    attempts = info["attempts"]
    success = info["success"]
    if attempts <= STEAL_CHANCE_BEGINNER_ATTEMPTS:
        info["chance"] = STEAL_CHANCE_BEGINNER
    elif attempts <= STEAL_CHANCE_INTERMEDIATE_ATTEMPTS:
        info["chance"] = STEAL_CHANCE_INTERMEDIATE
    elif attempts >= STEAL_CHANCE_MIN_ATTEMPTS_FOR_BONUS:
        success_count = success
        if success_count <= STEAL_CHANCE_SUCCESS_LINEAR_CAP:
            chance = STEAL_CHANCE_BASE + success_count
            info["chance"] = min(chance, STEAL_CHANCE_LINEAR_MAX)
        else:
            bonus = 0
            bonus += (success_count - STEAL_CHANCE_SUCCESS_LINEAR_CAP) // 2
            bonus += (success_count - STEAL_CHANCE_SUCCESS_LINEAR_CAP) // 4
            bonus += (success_count - STEAL_CHANCE_SUCCESS_LINEAR_CAP) // 10
            info["chance"] = min(STEAL_CHANCE_LINEAR_MAX + bonus, STEAL_CHANCE_ABSOLUTE_MAX)


def calculate_princess_amount(chance: int) -> int:
    for max_chance, min_loot, max_loot in STEAL_LOOT_TIERS:
        if chance <= max_chance:
            return random.randint(min_loot, max_loot)
    _, min_loot, max_loot = STEAL_LOOT_TIERS[-1]
    return random.randint(min_loot, max_loot)


def get_daily_bonus(day_number: int) -> int:
    return DAILY_BONUS_MAP.get(day_number, DAILY_BONUS_DEFAULT)


def is_steal_allowed() -> bool:
    return now_msk().weekday() in STEAL_ALLOWED_WEEKDAYS


def prison_chance_for_amount(stolen: int) -> int:
    for min_amount, max_amount, chance in PRISON_CHANCE_TIERS:
        if min_amount <= stolen <= max_amount:
            return chance
    return 0
