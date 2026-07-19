"""Расчёт коэффициентов перед забегом."""

from __future__ import annotations

from bot.db import Database
from bot.db.races import LineupEntry, RacesBet

from . import settings
from .lineup import format_horse_mark
from .settings import (
    ALPHA,
    BASE_ODDS,
    BETA,
    MAX_COEFFICIENT,
    MIN_COEFFICIENT,
)

# «Подушка» на каждую лошадь: одна ночная ставка не даёт share=100%.
# При большом живом банке фантом почти не влияет.
PHANTOM_BET_PER_HORSE = int(getattr(settings, "PHANTOM_BET_PER_HORSE", 500))


async def compute_odds(
    db: Database,
    lineup: list[LineupEntry],
    bet_list: list[RacesBet],
) -> dict[int, float]:
    total_bets = sum(b.amount for b in bet_list) or 0
    bet_sums: dict[int, int] = {}
    for bet in bet_list:
        bet_sums[bet.horse_number] = bet_sums.get(bet.horse_number, 0) + bet.amount

    n = max(1, len(lineup))
    phantom = max(0, PHANTOM_BET_PER_HORSE)
    effective_total = total_bets + phantom * n

    from bot.db import races as races_db

    odds: dict[int, float] = {}
    for entry in lineup:
        horse = entry.horse_number
        effective_on_horse = bet_sums.get(horse, 0) + phantom
        share = effective_on_horse / max(1, effective_total)
        stats = await races_db.get_princess_stats(db, entry.princess_name)
        win_rate = stats.wins_count / max(1, stats.races_count)
        raw = BASE_ODDS / (1 + ALPHA * share + BETA * win_rate)
        odds[horse] = max(MIN_COEFFICIENT, min(MAX_COEFFICIENT, raw))
    return odds


def format_odds_line(
    entries: list[LineupEntry],
    odds_map: dict[int, float],
) -> str:
    """Одна строка для чата: пояснение + ① Имя — ×к."""
    parts: list[str] = []
    for entry in sorted(entries, key=lambda e: e.horse_number):
        coeff = odds_map.get(entry.horse_number)
        if coeff is None:
            continue
        mark = format_horse_mark(entry.horse_number)
        parts.append(f"{mark} {entry.princess_name} — ×{coeff:.1f}")
    body = " · ".join(parts) if parts else "нет данных"
    return f"Чем популярнее принцесса, тем ниже коэффициент. {body}"
