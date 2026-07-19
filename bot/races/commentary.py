"""Итоговые сообщения забега в чат (без live-сводок во время гонки)."""

from __future__ import annotations

from .lineup import format_horse_mark


def format_podium_suffix(
    finish_order: list[int],
    name_by_horse: dict[int, str],
) -> str:
    """2-е и 3-е место для итогового сообщения."""
    parts: list[str] = []
    if len(finish_order) >= 2:
        horse = finish_order[1]
        parts.append(
            f"2-е — {format_horse_mark(horse)} {name_by_horse.get(horse, '?')}"
        )
    if len(finish_order) >= 3:
        horse = finish_order[2]
        parts.append(
            f"3-е — {format_horse_mark(horse)} {name_by_horse.get(horse, '?')}"
        )
    if not parts:
        return ""
    return ", ".join(parts)


def format_finish_header(
    winner_horse: int,
    winner_name: str,
    coeff: float,
    finish_order: list[int],
    name_by_horse: dict[int, str],
) -> str:
    header = (
        f"Финиш! Победила {format_horse_mark(winner_horse)} {winner_name} "
        f"(коэфф. {coeff:.1f})!"
    )
    podium = format_podium_suffix(finish_order, name_by_horse)
    if podium:
        return f"{header} {podium}."
    return header
