"""Комментарии забега в чат."""

from __future__ import annotations

from .settings import (
    COMMENTARY_FLAVOR_MIN_TICK_GAP,
    COMMENTARY_STANDINGS_EVERY_TICKS,
    FINISH_LINE,
)
from .simulate import RaceEvent, RaceTick


def format_event(ev: RaceEvent) -> str:
    if ev.kind == "judge":
        return ev.message
    return f"№{ev.horse_number} {ev.princess_name}: {ev.message}"


def rank_horses(
    positions: dict[int, float],
    finish_order: list[int],
) -> list[int]:
    finished = list(finish_order)
    finished_set = set(finished)
    remaining = [h for h in positions if h not in finished_set]
    remaining.sort(key=lambda h: positions.get(h, 0.0), reverse=True)
    return finished + remaining


def format_standings(
    ranking: list[int],
    name_by_horse: dict[int, str],
    n: int = 3,
) -> str:
    parts = [
        f"№{horse} {name_by_horse.get(horse, '?')}"
        for horse in ranking[:n]
    ]
    return " · ".join(parts)


def _place_label(place: int) -> str:
    n = place % 100
    if 11 <= n <= 14:
        return f"{place}-е место"
    r = place % 10
    if r == 1:
        return f"{place}-е место"
    if 2 <= r <= 4:
        return f"{place}-е место"
    return f"{place}-е место"


def format_podium_suffix(
    finish_order: list[int],
    name_by_horse: dict[int, str],
) -> str:
    """2-е и 3-е место для итогового сообщения."""
    parts: list[str] = []
    if len(finish_order) >= 2:
        horse = finish_order[1]
        parts.append(f"2-е — №{horse} {name_by_horse.get(horse, '?')}")
    if len(finish_order) >= 3:
        horse = finish_order[2]
        parts.append(f"3-е — №{horse} {name_by_horse.get(horse, '?')}")
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
        f"Финиш! Победила №{winner_horse} {winner_name} "
        f"(коэфф. {coeff:.1f})!"
    )
    podium = format_podium_suffix(finish_order, name_by_horse)
    if podium:
        return f"{header} {podium}."
    return header


class RaceCommentator:
    def __init__(
        self,
        name_by_horse: dict[int, str],
        finish_line: float = FINISH_LINE,
    ) -> None:
        self._name_by_horse = name_by_horse
        self._finish_line = finish_line
        self._finish_order: list[int] = []
        self._finished: set[int] = set()
        self._last_flavor_tick = -COMMENTARY_FLAVOR_MIN_TICK_GAP

    def on_tick(self, tick: RaceTick) -> list[str]:
        messages: list[str] = []
        positions = tick.positions

        for horse, pos in positions.items():
            if horse in self._finished:
                continue
            if pos >= self._finish_line:
                self._finished.add(horse)
                self._finish_order.append(horse)
                place = len(self._finish_order)
                if place == 1:
                    name = self._name_by_horse.get(horse, "?")
                    messages.append(
                        f"№{horse} {name} финиширует! ({_place_label(place)})"
                    )

        if tick.last_event:
            ev = tick.last_event
            if ev.kind == "judge":
                if tick.tick - self._last_flavor_tick >= COMMENTARY_FLAVOR_MIN_TICK_GAP:
                    messages.append(format_event(ev))
                    self._last_flavor_tick = tick.tick
            else:
                messages.append(format_event(ev))

        ranking = rank_horses(positions, self._finish_order)
        active = [h for h in ranking if h not in self._finished]

        if tick.tick % COMMENTARY_STANDINGS_EVERY_TICKS == 0 and len(active) >= 2:
            messages.append(f"Гонка: {format_standings(ranking, self._name_by_horse)}")

        return messages
