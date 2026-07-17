"""Настройки модуля рыбалки. Скопируйте в settings.py при необходимости."""

from __future__ import annotations

from zoneinfo import ZoneInfo

FISHING_CMD = "!рыбалка"
MSK = ZoneInfo("Europe/Moscow")

ENERGY_MAX = 100
ENERGY_REGEN_INTERVAL_SEC = 36  # +1 энергия каждые 36 с → 100 за час
CAST_ENERGY_COST = 5
WORMS_ENERGY_COST = 15
WORMS_GAIN = 5
MAGGOT_COST = 50
MAGGOT_GAIN = 10
ROD_COST = 1000
CAST_COOLDOWN_SEC = 20

FIRST_FISH_BONUS = 500
MERMAID_PENALTY = 3000
SILT_ENERGY_LOSS = 10
SEAGULL_BAIT_MAX = 3

# Негативные события: взаимоисключающие шансы (сумма 0.06)
NEG_EVENT_CHANCES: dict[str, float] = {
    "mermaid": 0.01,
    "pike_break": 0.015,
    "seagull": 0.015,
    "silt": 0.01,
    "reeds": 0.01,
}

TRASH_CHANCE = 0.18  # среди исходов без негатива
# рыба = 1 - TRASH_CHANCE = 0.82

# Вид: (вес дропа, w_min, w_max, base_price)
FISH_SPECIES: dict[str, tuple[int, float, float, int]] = {
    "Карась": (28, 0.15, 0.80, 200),
    "Плотва": (22, 0.10, 0.55, 250),
    "Окунь": (18, 0.20, 1.20, 400),
    "Лещ": (12, 0.40, 2.00, 600),
    "Щука": (10, 0.80, 4.00, 900),
    "Сом": (6, 1.50, 8.00, 1400),
    "Осётр": (4, 2.00, 12.00, 2500),
}

SIZE_SMALL_MULT = 0.5
SIZE_MEDIUM_MULT = 1.0
SIZE_LARGE_MULT = 2.0
SIZE_SMALL_T = 0.40
SIZE_LARGE_T = 0.75

WEEK_REWARDS: dict[str, int] = {
    "Карась": 500,
    "Плотва": 600,
    "Окунь": 800,
    "Лещ": 1000,
    "Щука": 1500,
    "Сом": 2000,
    "Осётр": 3500,
}
FISH_OF_WEEK_BONUS = 2000

TRASH_TYPES = (
    "algae",
    "boot",
    "can",
    "snag",
    "bucket",
    "float",
)
