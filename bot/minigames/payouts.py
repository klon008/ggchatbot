"""Пропорциональное урезание выплат при банкротстве казны."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PayoutScaleResult:
    actual_amounts: list[int]
    total_ideal: int
    total_actual: int
    bankrupted: bool
    new_bank: int


def scale_payouts(ideal_amounts: list[int], bank_balance: int) -> PayoutScaleResult:
    """Распределить выплаты из казны; при нехватке — пропорционально урезать."""
    if not ideal_amounts:
        return PayoutScaleResult(
            actual_amounts=[],
            total_ideal=0,
            total_actual=0,
            bankrupted=False,
            new_bank=bank_balance,
        )

    total_ideal = sum(ideal_amounts)
    positives = [max(0, a) for a in ideal_amounts]
    total_ideal = sum(positives)

    if total_ideal <= 0:
        return PayoutScaleResult(
            actual_amounts=[0] * len(ideal_amounts),
            total_ideal=0,
            total_actual=0,
            bankrupted=False,
            new_bank=bank_balance,
        )

    if total_ideal <= bank_balance:
        return PayoutScaleResult(
            actual_amounts=positives,
            total_ideal=total_ideal,
            total_actual=total_ideal,
            bankrupted=False,
            new_bank=bank_balance - total_ideal,
        )

    coefficient = bank_balance / total_ideal
    actual_amounts = [int(a * coefficient) for a in positives]
    total_actual = sum(actual_amounts)
    return PayoutScaleResult(
        actual_amounts=actual_amounts,
        total_ideal=total_ideal,
        total_actual=total_actual,
        bankrupted=True,
        new_bank=0,
    )
