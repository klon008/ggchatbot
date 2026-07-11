"""Выплаты по коэффициентам скачек."""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.races import RacesBet
from bot.minigames import payouts as shared_payouts


@dataclass
class WinnerPayout:
    user_id: str
    user_name: str
    horse_number: int
    ideal: int
    actual: int


@dataclass
class PayoutResult:
    winners: list[WinnerPayout]
    total_ideal: int
    total_actual: int
    bankrupted: bool
    new_bank: int


def calculate_payouts(
    bet_list: list[RacesBet],
    winner_horse: int,
    odds: dict[int, float],
    bank_balance: int,
) -> PayoutResult:
    winners: list[WinnerPayout] = []
    ideals: list[int] = []

    for bet in bet_list:
        if bet.horse_number != winner_horse:
            continue
        coeff = odds.get(bet.horse_number, 1.0)
        ideal = int(bet.amount * coeff)
        if ideal <= 0:
            continue
        winners.append(
            WinnerPayout(
                user_id=bet.user_id,
                user_name=bet.user_name,
                horse_number=bet.horse_number,
                ideal=ideal,
                actual=ideal,
            )
        )
        ideals.append(ideal)

    scaled = shared_payouts.scale_payouts(ideals, bank_balance)
    for w, actual in zip(winners, scaled.actual_amounts):
        w.actual = actual

    return PayoutResult(
        winners=winners,
        total_ideal=scaled.total_ideal,
        total_actual=scaled.total_actual,
        bankrupted=scaled.bankrupted,
        new_bank=scaled.new_bank,
    )
