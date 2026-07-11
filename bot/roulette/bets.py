"""Парсинг и проверка ставок !рулетка."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from . import wheel
from .settings import (
    ROULETTE_MAX_BET,
    ROULETTE_MAX_NUMBERS,
    ROULETTE_MIN_BET,
)

RULES_TEXT = (
    "!рулетка <сумма> [<число> | красное/черное | четное/нечетное | "
    "малые/большие | 0] — один раунд на чат, одна ставка на игрока, ~60 сек на приём."
)

_COLOR_WORDS = {
    "красное": "red",
    "черное": "black",
    "чёрное": "black",
}
_PARITY_WORDS = {
    "четное": "even",
    "чётное": "even",
    "нечетное": "odd",
    "нечётное": "odd",
}
_HALF_WORDS = {
    "малые": "low",
    "большие": "high",
}


@dataclass
class ParsedBet:
    amount: int
    bet_type: str
    bet_payload: dict


@dataclass
class ParseError:
    message: str


def parse_bet_command(text: str) -> ParsedBet | ParseError:
    stripped = text.strip()
    lower = stripped.lower()
    if lower == "!рулетка правила":
        return ParseError("__rules__")

    if not lower.startswith("!рулетка"):
        return ParseError("Неизвестная команда.")

    rest = stripped[len("!рулетка"):].strip()
    if not rest:
        return ParseError("Укажите сумму и тип ставки.")

    parts = rest.split(maxsplit=1)
    if len(parts) < 2:
        return ParseError("Укажите сумму и тип ставки.")

    amount_raw, target = parts[0], parts[1].strip()
    if not amount_raw.isdigit():
        return ParseError("Сумма ставки должна быть целым числом.")
    amount = int(amount_raw)
    if amount < ROULETTE_MIN_BET:
        return ParseError(f"Минимальная ставка — {ROULETTE_MIN_BET} балл.")
    if amount > ROULETTE_MAX_BET:
        return ParseError(f"Максимальная ставка — {ROULETTE_MAX_BET} баллов.")

    target_lower = target.lower()

    if target_lower.startswith("на "):
        numbers_part = target[3:].strip()
        return _parse_numbers_bet(amount, numbers_part)

    if _looks_like_numbers(target):
        return _parse_numbers_bet(amount, target)

    if target_lower in _COLOR_WORDS:
        return ParsedBet(amount, "color", {"color": _COLOR_WORDS[target_lower]})

    if target_lower in _PARITY_WORDS:
        return ParsedBet(amount, "parity", {"parity": _PARITY_WORDS[target_lower]})

    if target_lower in _HALF_WORDS:
        return ParsedBet(amount, "half", {"half": _HALF_WORDS[target_lower]})

    return ParseError(
        "Формат: !рулетка <сумма> <число> | на <число> | красное/черное | "
        "четное/нечетное | малые/большие"
    )


def _looks_like_numbers(text: str) -> bool:
    items = [p.strip() for p in text.split(",") if p.strip()]
    if not items:
        return False
    return all(re.fullmatch(r"\d+", item) for item in items)


def _parse_numbers_bet(amount: int, numbers_part: str) -> ParsedBet | ParseError:
    if not numbers_part:
        return ParseError("Укажите число или список чисел через запятую.")
    raw_items = [p.strip() for p in numbers_part.split(",") if p.strip()]
    if not raw_items:
        return ParseError("Укажите число или список чисел через запятую.")
    if len(raw_items) > ROULETTE_MAX_NUMBERS:
        return ParseError("Нельзя ставить более чем на 18 чисел одновременно!")

    numbers: list[int] = []
    for item in raw_items:
        if not re.fullmatch(r"\d+", item):
            return ParseError("Число должно быть от 0 до 36.")
        value = int(item)
        if value < 0 or value > 36:
            return ParseError("Число должно быть от 0 до 36.")
        if value in numbers:
            return ParseError("Числа в ставке не должны повторяться.")
        numbers.append(value)

    return ParsedBet(amount, "numbers", {"numbers": numbers})


def bet_label(bet_type: str, payload: dict) -> str:
    if bet_type == "numbers":
        nums = ",".join(str(n) for n in payload["numbers"])
        return f"на {nums}"
    if bet_type == "color":
        return "красное" if payload["color"] == "red" else "черное"
    if bet_type == "parity":
        return "четное" if payload["parity"] == "even" else "нечетное"
    if bet_type == "half":
        return "малые" if payload["half"] == "low" else "большие"
    return bet_type


def is_winner(bet_type: str, payload: dict, number: int) -> bool:
    color = wheel.color_of(number)
    if bet_type == "numbers":
        return number in payload["numbers"]
    if bet_type == "color":
        return color == payload["color"]
    if bet_type == "parity":
        if number == 0:
            return False
        is_even = number % 2 == 0
        return is_even if payload["parity"] == "even" else not is_even
    if bet_type == "half":
        if number == 0:
            return False
        if payload["half"] == "low":
            return 1 <= number <= 18
        return 19 <= number <= 36
    return False


def ideal_payout(amount: int, bet_type: str, payload: dict) -> int:
    if bet_type == "numbers":
        n = len(payload["numbers"])
        return amount * 36 // n
    if bet_type in ("color", "parity", "half"):
        return amount * 2
    return 0
