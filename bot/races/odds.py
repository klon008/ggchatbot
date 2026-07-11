"""Расчёт коэффициентов перед забегом."""

from __future__ import annotations

from bot.db import Database
from bot.db.races import LineupEntry, RacesBet

from .settings import (
    ALPHA,
    BASE_ODDS,
    BETA,
    MAX_COEFFICIENT,
    MIN_COEFFICIENT,
)


async def compute_odds(
    db: Database,
    lineup: list[LineupEntry],
    bet_list: list[RacesBet],
) -> dict[int, float]:
    total_bets = sum(b.amount for b in bet_list) or 0
    bet_sums: dict[int, int] = {}
    for bet in bet_list:
        bet_sums[bet.horse_number] = bet_sums.get(bet.horse_number, 0) + bet.amount

    from bot.db import races as races_db

    odds: dict[int, float] = {}
    for entry in lineup:
        horse = entry.horse_number
        share = bet_sums.get(horse, 0) / max(1, total_bets)
        stats = await races_db.get_princess_stats(db, entry.princess_name)
        win_rate = stats.wins_count / max(1, stats.races_count)
        raw = BASE_ODDS / (1 + ALPHA * share + BETA * win_rate)
        odds[horse] = max(MIN_COEFFICIENT, min(MAX_COEFFICIENT, raw))
    return odds
