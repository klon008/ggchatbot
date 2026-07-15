"""Парсинг и проверка ставок !забег."""

from __future__ import annotations

from dataclasses import dataclass

from . import settings
from .settings import RACES_COLLECT_SEC, RACES_MAX_BET, RACES_MIN_BET, RUNNERS_COUNT

PLACE2_PAYOUT_RATIO = getattr(settings, "PLACE2_PAYOUT_RATIO", 0.30)
PLACE3_PAYOUT_RATIO = getattr(settings, "PLACE3_PAYOUT_RATIO", 0.10)

RACE_CMD = "!забег"
RACE_RULES_CMD = f"{RACE_CMD} правила"
RACE_ADMIN_BANK_CMD = f"{RACE_CMD}_банк"
RACE_ADMIN_TOPUP_CMD = f"{RACE_CMD}_пополнить"
RACE_ADMIN_RESET_CMD = f"{RACE_CMD}_сброс"

RULES_TEXT = (
    f"{RACE_CMD} — открыть забег и показать состав (№1–{RUNNERS_COUNT}); "
    f"{RACE_CMD} <сумма> <1–{RUNNERS_COUNT}> — ставка после просмотра состава. "
    f"Один забег на чат, одна ставка на игрока, ~{RACES_COLLECT_SEC} сек на приём. "
    "Выигрыш = ставка × коэффициент (чем популярнее лошадь, тем ниже коэффициент). "
    f"За 2-е место — {int(PLACE2_PAYOUT_RATIO * 100)}% от полного выигрыша, "
    f"за 3-е — {int(PLACE3_PAYOUT_RATIO * 100)}%."
)


@dataclass
class ParsedBet:
    amount: int
    horse_number: int


@dataclass
class ParseError:
    message: str


def parse_bet_command(text: str) -> ParsedBet | ParseError:
    parts = text.strip().split()
    if len(parts) < 3:
        return ParseError(
            f"Формат ставки: {RACE_CMD} <сумма> <номер 1–{RUNNERS_COUNT}>. "
            f"Сначала откройте забег командой {RACE_CMD}."
        )

    cmd = parts[0].lower()
    if cmd != RACE_CMD:
        return ParseError(
            f"Формат ставки: {RACE_CMD} <сумма> <номер лошади 1–{RUNNERS_COUNT}>"
        )

    if not parts[1].isdigit():
        return ParseError("Сумма ставки должна быть целым числом.")
    amount = int(parts[1])
    if amount < RACES_MIN_BET:
        return ParseError(f"Минимальная ставка — {RACES_MIN_BET} балл.")
    if amount > RACES_MAX_BET:
        return ParseError(f"Максимальная ставка — {RACES_MAX_BET} баллов.")

    if not parts[2].isdigit():
        return ParseError(f"Номер лошади должен быть от 1 до {RUNNERS_COUNT}.")
    horse_number = int(parts[2])
    if horse_number < 1 or horse_number > RUNNERS_COUNT:
        return ParseError(f"Номер лошади должен быть от 1 до {RUNNERS_COUNT}.")

    return ParsedBet(amount=amount, horse_number=horse_number)
