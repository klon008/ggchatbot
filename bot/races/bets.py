"""Парсинг и проверка ставок !скачки."""

from __future__ import annotations

from dataclasses import dataclass

from .settings import RACES_COLLECT_SEC, RACES_MAX_BET, RACES_MIN_BET, RUNNERS_COUNT

RULES_TEXT = (
    f"!скачки — открыть забег и показать состав (№1–{RUNNERS_COUNT}); "
    f"!скачки <сумма> <1–{RUNNERS_COUNT}> — ставка после просмотра состава. "
    f"Один забег на чат, одна ставка на игрока, ~{RACES_COLLECT_SEC} сек на приём. "
    "Выигрыш = ставка × коэффициент (чем популярнее лошадь, тем ниже коэффициент)."
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
            f"Формат ставки: !скачки <сумма> <номер 1–{RUNNERS_COUNT}>. "
            "Сначала откройте забег командой !скачки."
        )

    cmd = parts[0].lower()
    if cmd != "!скачки":
        return ParseError(f"Формат ставки: !скачки <сумма> <номер лошади 1–{RUNNERS_COUNT}>")

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
