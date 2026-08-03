"""Quick unit checks for steal economy math (run: python scripts/test_steal_economy.py)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.princess.economy import (
    apply_attempt_growth,
    apply_missed_day_decay,
    chance_ceiling_from_attempts,
    loot_tiers_from_dict,
    roll_steal_amount,
)
from bot.princess.settings import STEAL_CHANCE_CAP, STEAL_CHANCE_FLOOR


def test_growth() -> None:
    info = {"attempts": 0, "chance": STEAL_CHANCE_FLOOR}
    for n in range(1, 11):
        info["attempts"] = n
        apply_attempt_growth(info)
    assert info["chance"] == 7, info  # +1 at 5, +1 at 10
    assert chance_ceiling_from_attempts(5) == 6
    assert chance_ceiling_from_attempts(10) == 7
    assert chance_ceiling_from_attempts(150) == STEAL_CHANCE_CAP


def test_miss_decay() -> None:
    info = {"chance": 20, "last_steal_day_key": "2026-08-01"}
    assert apply_missed_day_decay(info, "2026-08-05") is True
    assert info["chance"] == 18
    info["last_steal_day_key"] = "2026-08-05"
    assert apply_missed_day_decay(info, "2026-08-05") is False
    info = {"chance": STEAL_CHANCE_FLOOR, "last_steal_day_key": ""}
    assert apply_missed_day_decay(info, "2026-08-05") is False
    assert info["chance"] == STEAL_CHANCE_FLOOR
    info = {"chance": 6, "last_steal_day_key": ""}
    assert apply_missed_day_decay(info, "x") is True
    assert info["chance"] == STEAL_CHANCE_FLOOR


def test_loot_parse() -> None:
    bad = loot_tiers_from_dict(
        {
            "meloch": {"weight": 0, "min": 1, "max": 2},
            "normal": {"weight": 0, "min": 1, "max": 2},
            "zhir": {"weight": 0, "min": 1, "max": 2},
            "kush": {"weight": 0, "min": 1, "max": 2},
        }
    )
    assert bad is None
    good = loot_tiers_from_dict(
        {
            "meloch": {"weight": 50, "min": 100, "max": 400},
            "normal": {"weight": 30, "min": 400, "max": 900},
            "zhir": {"weight": 15, "min": 900, "max": 1600},
            "kush": {"weight": 5, "min": 1600, "max": 2500},
        }
    )
    assert good is not None
    amt = roll_steal_amount(good)
    assert 100 <= amt <= 2500


if __name__ == "__main__":
    test_growth()
    test_miss_decay()
    test_loot_parse()
    print("ok")
