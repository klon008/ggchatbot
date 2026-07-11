"""Европейская рулетка 0–36: цвета и спин."""

from __future__ import annotations

import random

RED_NUMBERS = frozenset({
    1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36,
})
BLACK_NUMBERS = frozenset({
    2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35,
})


def color_of(number: int) -> str:
    if number == 0:
        return "green"
    if number in RED_NUMBERS:
        return "red"
    if number in BLACK_NUMBERS:
        return "black"
    raise ValueError(f"invalid roulette number: {number}")


def color_label_ru(color: str) -> str:
    return {"red": "красное", "black": "чёрное", "green": "зелёное"}[color]


def spin() -> int:
    return random.randint(0, 36)


def format_result(number: int) -> str:
    color = color_of(number)
    if color == "green":
        return f"{number} {color_label_ru(color)}"
    return f"{number} {color_label_ru(color)}"
