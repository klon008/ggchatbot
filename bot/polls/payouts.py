"""Peer-pool выплаты для опросов (Twitch Predictions style)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WinnerPayout:
    user_id: str
    user_name: str
    stake: int
    payout: int
    option_index: int


@dataclass
class PayoutResult:
    winners: list[WinnerPayout]
    total_pool: int
    winners_pool: int
    losers_pool: int
    winning_option: int


def calculate_payouts(
    bets: list,
    winning_option: int,
) -> PayoutResult:
    """Распределить весь банк: победители получают stake + долю проигравших.

    bets: объекты с .user_id, .user_name, .amount, .option_index
    """
    total_pool = sum(int(b.amount) for b in bets)
    winners = [b for b in bets if int(b.option_index) == int(winning_option)]
    losers = [b for b in bets if int(b.option_index) != int(winning_option)]
    winners_pool = sum(int(b.amount) for b in winners)
    losers_pool = sum(int(b.amount) for b in losers)

    if not winners:
        return PayoutResult(
            winners=[],
            total_pool=total_pool,
            winners_pool=0,
            losers_pool=losers_pool,
            winning_option=winning_option,
        )

    # Все на победившей стороне — возврат stake (×1)
    if losers_pool <= 0 or winners_pool <= 0:
        result_winners = [
            WinnerPayout(
                user_id=str(b.user_id),
                user_name=str(b.user_name),
                stake=int(b.amount),
                payout=int(b.amount),
                option_index=int(b.option_index),
            )
            for b in winners
        ]
        return PayoutResult(
            winners=result_winners,
            total_pool=total_pool,
            winners_pool=winners_pool,
            losers_pool=losers_pool,
            winning_option=winning_option,
        )

    # Базовая формула + remainder по +1 сверху вниз (по убыванию stake)
    ordered = sorted(winners, key=lambda b: (-int(b.amount), str(b.user_id)))
    base_payouts: list[int] = []
    for b in ordered:
        stake = int(b.amount)
        share = (stake * losers_pool) // winners_pool
        base_payouts.append(stake + share)

    distributed_extra = sum(p - int(b.amount) for p, b in zip(base_payouts, ordered))
    remainder = losers_pool - distributed_extra
    idx = 0
    while remainder > 0 and ordered:
        base_payouts[idx % len(ordered)] += 1
        remainder -= 1
        idx += 1

    result_winners = [
        WinnerPayout(
            user_id=str(b.user_id),
            user_name=str(b.user_name),
            stake=int(b.amount),
            payout=payout,
            option_index=int(b.option_index),
        )
        for b, payout in zip(ordered, base_payouts)
    ]
    return PayoutResult(
        winners=result_winners,
        total_pool=total_pool,
        winners_pool=winners_pool,
        losers_pool=losers_pool,
        winning_option=winning_option,
    )


def option_coefficient(option_total: int, total_pool: int) -> float:
    """Потенциальный множитель: 1 + losers/winners для варианта."""
    if option_total <= 0 or total_pool <= 0:
        return 1.0
    losers = total_pool - option_total
    return 1.0 + (losers / option_total)
