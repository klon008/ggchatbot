"""Календарь, реген энергии, продажа и размеры."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from .settings import (
    ENERGY_MAX,
    ENERGY_REGEN_INTERVAL_SEC,
    FISH_SPECIES,
    MSK,
    SIZE_LARGE_MULT,
    SIZE_LARGE_T,
    SIZE_MEDIUM_MULT,
    SIZE_SMALL_MULT,
    SIZE_SMALL_T,
)


def now_msk() -> datetime:
    return datetime.now(MSK)


def day_key(dt: datetime | None = None) -> str:
    return (dt or now_msk()).strftime("%Y-%m-%d")


def week_id(dt: datetime | None = None) -> str:
    """ISO-неделя по календарю MSK (понедельник — начало)."""
    d = dt or now_msk()
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def apply_energy_regen(player: dict[str, Any], now_ts: float | None = None) -> dict[str, Any]:
    now = time.time() if now_ts is None else now_ts
    energy = int(player["energy"])
    updated = float(player["energy_updated_at"] or 0)
    if energy >= ENERGY_MAX:
        player["energy"] = ENERGY_MAX
        player["energy_updated_at"] = now
        return player
    if updated <= 0:
        player["energy_updated_at"] = now
        return player
    elapsed = max(0.0, now - updated)
    gained = int(elapsed // ENERGY_REGEN_INTERVAL_SEC)
    if gained <= 0:
        return player
    energy = min(ENERGY_MAX, energy + gained)
    player["energy"] = energy
    player["energy_updated_at"] = updated + gained * ENERGY_REGEN_INTERVAL_SEC
    if energy >= ENERGY_MAX:
        player["energy_updated_at"] = now
    return player


def size_bucket(weight: float, w_min: float, w_max: float) -> tuple[str, float]:
    span = w_max - w_min
    if span <= 0:
        t = 1.0
    else:
        t = (weight - w_min) / span
    if t < SIZE_SMALL_T:
        return "мелкий", SIZE_SMALL_MULT
    if t < SIZE_LARGE_T:
        return "средний", SIZE_MEDIUM_MULT
    return "крупный", SIZE_LARGE_MULT


def sell_price(species: str, weight: float) -> tuple[str, int]:
    _, w_min, w_max, base = FISH_SPECIES[species]
    size, mult = size_bucket(weight, w_min, w_max)
    return size, int(base * mult)


def new_player(user_id: str, user_name: str, now_ts: float | None = None) -> dict[str, Any]:
    now = time.time() if now_ts is None else now_ts
    return {
        "user_id": str(user_id),
        "user_name": user_name,
        "energy": ENERGY_MAX,
        "energy_updated_at": now,
        "worms": 0,
        "maggots": 0,
        "rod_state": "none",
        "last_cast_at": 0.0,
        "day_key": day_key(),
    }
