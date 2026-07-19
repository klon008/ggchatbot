"""Выплаты по коэффициентам скачек."""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.races import RacesBet
from bot.minigames import payouts as shared_payouts

from . import settings

PLACE2_PAYOUT_RATIO = getattr(settings, "PLACE2_PAYOUT_RATIO", 0.30)
PLACE3_PAYOUT_RATIO = getattr(settings, "PLACE3_PAYOUT_RATIO", 0.10)


@dataclass
class WinnerPayout:
    user_id: str
    user_name: str
    horse_number: int
    place: int
    ideal: int
    actual: int


@dataclass
class PayoutResult:
    winners: list[WinnerPayout]
    total_ideal: int
    total_actual: int
    bankrupted: bool
    new_bank: int


def _ideal_for_place(full_win: int, stake: int, place: int) -> int:
    """1-е: полный выигрыш; 2–3: доля от полного, но не меньше возврата ставки."""
    if place == 1:
        return full_win
    if place == 2:
        return max(stake, int(full_win * PLACE2_PAYOUT_RATIO))
    if place == 3:
        return max(stake, int(full_win * PLACE3_PAYOUT_RATIO))
    return 0


def calculate_payouts(
    bet_list: list[RacesBet],
    finish_order: list[int],
    odds: dict[int, float],
    bank_balance: int,
) -> PayoutResult:
    winners: list[WinnerPayout] = []
    ideals: list[int] = []
    place_by_horse = {horse: idx + 1 for idx, horse in enumerate(finish_order[:3])}

    for bet in bet_list:
        place = place_by_horse.get(bet.horse_number)
        if place is None:
            continue
        coeff = odds.get(bet.horse_number, 1.0)
        full_win = int(bet.amount * coeff)
        ideal = _ideal_for_place(full_win, bet.amount, place)
        if ideal <= 0:
            continue
        winners.append(
            WinnerPayout(
                user_id=bet.user_id,
                user_name=bet.user_name,
                horse_number=bet.horse_number,
                place=place,
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
