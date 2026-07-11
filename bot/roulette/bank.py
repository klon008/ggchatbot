"""Расчёт выплат из казны рулетки."""

from __future__ import annotations

from dataclasses import dataclass

from bot.db.roulette import RouletteBet

from . import bets


@dataclass
class WinnerPayout:
    user_id: str
    user_name: str
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
    bet_list: list[RouletteBet],
    result_number: int,
    bank_balance: int,
) -> PayoutResult:
    winners: list[WinnerPayout] = []
    total_ideal = 0

    for bet in bet_list:
        if not bets.is_winner(bet.bet_type, bet.bet_payload, result_number):
            continue
        ideal = bets.ideal_payout(bet.amount, bet.bet_type, bet.bet_payload)
        if ideal <= 0:
            continue
        winners.append(
            WinnerPayout(
                user_id=bet.user_id,
                user_name=bet.user_name,
                ideal=ideal,
                actual=ideal,
            )
        )
        total_ideal += ideal

    if not winners:
        return PayoutResult(
            winners=[],
            total_ideal=0,
            total_actual=0,
            bankrupted=False,
            new_bank=bank_balance,
        )

    if total_ideal <= bank_balance:
        total_actual = total_ideal
        return PayoutResult(
            winners=winners,
            total_ideal=total_ideal,
            total_actual=total_actual,
            bankrupted=False,
            new_bank=bank_balance - total_actual,
        )

    coefficient = bank_balance / total_ideal
    total_actual = 0
    for w in winners:
        w.actual = int(w.ideal * coefficient)
        total_actual += w.actual

    return PayoutResult(
        winners=winners,
        total_ideal=total_ideal,
        total_actual=total_actual,
        bankrupted=True,
        new_bank=0,
    )
