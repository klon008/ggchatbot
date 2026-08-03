"""Игровая математика: шансы, бонусы, склонения."""
from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Optional, Sequence

from .settings import (
    DAILY_BONUS_DEFAULT,
    DAILY_BONUS_MAP,
    MSK,
    PRISON_CHANCE_TIERS,
    STEAL_ALLOWED_WEEKDAYS,
    STEAL_CHANCE_ATTEMPTS_DIV,
    STEAL_CHANCE_CAP,
    STEAL_CHANCE_FLOOR,
    STEAL_DECAY_MISSED_DAY_PCT,
    STEAL_LOOT_TIER_KEYS,
    STEAL_LOOT_TIERS,
)

LootTier = tuple[int, int, int]  # weight, min, max


def now_msk() -> datetime:
    return datetime.now(MSK)


def apply_attempt_growth(info: dict) -> None:
    """Вызывать после info['attempts'] += 1. +1% каждые N попыток, не выше капа."""
    attempts = int(info["attempts"])
    if attempts <= 0 or attempts % STEAL_CHANCE_ATTEMPTS_DIV != 0:
        return
    info["chance"] = min(
        STEAL_CHANCE_CAP,
        int(info.get("chance") or STEAL_CHANCE_FLOOR) + 1,
    )


def chance_ceiling_from_attempts(attempts: int) -> int:
    """Потолок шанса от attempts (без учёта missed decay). Для тестов/отображения."""
    return min(
        STEAL_CHANCE_CAP,
        STEAL_CHANCE_FLOOR + max(0, attempts) // STEAL_CHANCE_ATTEMPTS_DIV,
    )


def apply_missed_day_decay(info: dict, day_key: str) -> bool:
    """
    day_key — прошедший день кражи (ср/пт).
    Если last_steal_day_key != day_key → −STEAL_DECAY_MISSED_DAY_PCT%, пол FLOOR.
    """
    if info.get("last_steal_day_key") == day_key:
        return False
    cur = int(info.get("chance") or STEAL_CHANCE_FLOOR)
    if cur <= STEAL_CHANCE_FLOOR:
        return False
    info["chance"] = max(STEAL_CHANCE_FLOOR, cur - STEAL_DECAY_MISSED_DAY_PCT)
    return True


def default_loot_tiers() -> list[LootTier]:
    return [(int(w), int(lo), int(hi)) for w, lo, hi in STEAL_LOOT_TIERS]


def default_loot_tiers_dict() -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for key, (weight, lo, hi) in zip(STEAL_LOOT_TIER_KEYS, STEAL_LOOT_TIERS):
        out[key] = {"weight": int(weight), "min": int(lo), "max": int(hi)}
    return out


def loot_tiers_from_dict(data: dict[str, Any]) -> Optional[list[LootTier]]:
    """Parse named tiers dict → list of (weight, min, max). None if invalid."""
    if not isinstance(data, dict):
        return None
    tiers: list[LootTier] = []
    total_w = 0
    for key in STEAL_LOOT_TIER_KEYS:
        item = data.get(key)
        if not isinstance(item, dict):
            return None
        try:
            weight = int(item.get("weight", 0))
            lo = int(item.get("min", 0))
            hi = int(item.get("max", 0))
        except (TypeError, ValueError):
            return None
        if weight < 0 or lo > hi:
            return None
        tiers.append((weight, lo, hi))
        total_w += weight
    if total_w <= 0:
        return None
    return tiers


def loot_tiers_to_dict(tiers: Sequence[LootTier]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for key, (weight, lo, hi) in zip(STEAL_LOOT_TIER_KEYS, tiers):
        out[key] = {"weight": int(weight), "min": int(lo), "max": int(hi)}
    return out


def effective_loot_tiers(override: Optional[dict[str, Any]]) -> list[LootTier]:
    """Override из БД или дефолты settings."""
    if override:
        parsed = loot_tiers_from_dict(override)
        if parsed is not None:
            return parsed
    return default_loot_tiers()


def roll_steal_amount(tiers: Sequence[LootTier] | None = None) -> int:
    pool = list(tiers) if tiers else default_loot_tiers()
    total_w = sum(t[0] for t in pool)
    if total_w <= 0:
        pool = default_loot_tiers()
        total_w = sum(t[0] for t in pool)
    r = random.uniform(0, total_w)
    acc = 0.0
    for weight, lo, hi in pool:
        acc += weight
        if r <= acc:
            return random.randint(lo, hi)
    _, lo, hi = pool[-1]
    return random.randint(lo, hi)


def get_daily_bonus(day_number: int) -> int:
    return DAILY_BONUS_MAP.get(day_number, DAILY_BONUS_DEFAULT)


def is_steal_schedule_day() -> bool:
    """True, если сегодня день кражи по расписанию (MSK)."""
    return now_msk().weekday() in STEAL_ALLOWED_WEEKDAYS


def is_steal_allowed() -> bool:
    """Только расписание. Полная проверка (с override) — StealStore.is_allowed()."""
    return is_steal_schedule_day()


def prison_chance_for_amount(stolen: int) -> int:
    for min_amount, max_amount, chance in PRISON_CHANCE_TIERS:
        if min_amount <= stolen <= max_amount:
            return chance
    return 0
