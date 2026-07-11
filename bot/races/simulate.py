"""Симуляция забега с событиями."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from bot.db.races import LineupEntry

from .settings import (
    FINISH_LINE,
    RACE_EVENT_CHANCE,
    RACE_MOMENTUM_BLEND,
    RACE_PACE_SPREAD,
    RACE_SPEED_MAX,
    RACE_SPEED_MIN,
    RACE_TICKS,
    RACE_WIN_RATE_BONUS,
    STUMBLE_STUCK_MAX,
    STUMBLE_STUCK_MIN,
)


@dataclass
class RaceEvent:
    horse_number: int
    princess_name: str
    kind: str
    message: str


@dataclass
class RaceTick:
    tick: int
    positions: dict[int, float]
    last_event: Optional[RaceEvent] = None


@dataclass
class RaceResult:
    winner_horse: int
    winner_name: str
    finish_order: list[int]
    ticks: list[RaceTick] = field(default_factory=list)
    events: list[RaceEvent] = field(default_factory=list)


_MECHANICAL_EVENTS = [
    ("second_wind", "Открылось второе дыхание!"),
    ("stumble", "Споткнулась и упала!"),
    ("shortcut", "Срезала угол!"),
    ("tangle", "Запуталась в гриве!"),
    ("cheer", "Фанаты подбадривают!"),
]

_FLAVOR_MESSAGES = [
    "Судья следит за чистотой заезда!",
    "Кто-то машет флажком!",
    "Трибуны гудят!",
]


def _init_pace_factors(
    horses: list[int],
    win_rates: Optional[dict[int, float]] = None,
) -> dict[int, float]:
    factors: dict[int, float] = {}
    for horse in horses:
        talent = random.uniform(1.0 - RACE_PACE_SPREAD, 1.0 + RACE_PACE_SPREAD)
        wr = (win_rates or {}).get(horse, 0.0)
        history = 1.0 + RACE_WIN_RATE_BONUS * wr
        factors[horse] = talent * history
    return factors


def _roll_event(lineup: list[LineupEntry]) -> Optional[RaceEvent]:
    if random.random() > RACE_EVENT_CHANCE:
        return None
    entry = random.choice(lineup)
    if random.random() < 0.2:
        return RaceEvent(
            entry.horse_number,
            entry.princess_name,
            "judge",
            random.choice(_FLAVOR_MESSAGES),
        )
    kind, msg = random.choice(_MECHANICAL_EVENTS)
    return RaceEvent(entry.horse_number, entry.princess_name, kind, msg)


def _apply_event(
    ev: RaceEvent,
    *,
    stuck_remaining: dict[int, int],
    surge_remaining: dict[int, int],
    slow_remaining: dict[int, int],
    boost_remaining: dict[int, int],
) -> None:
    horse = ev.horse_number
    if ev.kind == "stumble":
        stuck_remaining[horse] = max(
            stuck_remaining.get(horse, 0),
            random.randint(STUMBLE_STUCK_MIN, STUMBLE_STUCK_MAX),
        )
    elif ev.kind == "second_wind":
        surge_remaining[horse] = max(surge_remaining.get(horse, 0), random.randint(4, 6))
    elif ev.kind == "tangle":
        slow_remaining[horse] = max(slow_remaining.get(horse, 0), random.randint(3, 5))
    elif ev.kind == "shortcut":
        surge_remaining[horse] = max(surge_remaining.get(horse, 0), random.randint(2, 3))
        boost_remaining[horse] = max(boost_remaining.get(horse, 0), 2)
    elif ev.kind == "cheer":
        boost_remaining[horse] = max(boost_remaining.get(horse, 0), random.randint(2, 4))


def _tick_delta(
    horse: int,
    *,
    pace_factors: dict[int, float],
    velocity: dict[int, float],
    stuck_remaining: dict[int, int],
    surge_remaining: dict[int, int],
    slow_remaining: dict[int, int],
    boost_remaining: dict[int, int],
) -> float:
    if stuck_remaining.get(horse, 0) > 0:
        stuck_remaining[horse] -= 1
        return 0.0

    noise = random.uniform(RACE_SPEED_MIN, RACE_SPEED_MAX)
    jitter = random.uniform(0.75, 1.35)
    target = noise * pace_factors[horse] * jitter

    velocity[horse] = (
        velocity[horse] * (1.0 - RACE_MOMENTUM_BLEND)
        + target * RACE_MOMENTUM_BLEND
    )
    delta = velocity[horse]

    if surge_remaining.get(horse, 0) > 0:
        surge_remaining[horse] -= 1
        delta *= random.uniform(2.0, 2.8)
    if slow_remaining.get(horse, 0) > 0:
        slow_remaining[horse] -= 1
        delta *= random.uniform(0.15, 0.4)
    if boost_remaining.get(horse, 0) > 0:
        boost_remaining[horse] -= 1
        delta *= random.uniform(1.4, 1.9)

    wild = random.random()
    if wild < 0.08:
        delta *= random.uniform(1.6, 2.4)
    elif wild < 0.14:
        delta *= random.uniform(0.05, 0.35)

    return delta


def simulate_race(
    lineup: list[LineupEntry],
    win_rates: Optional[dict[int, float]] = None,
) -> RaceResult:
    horses = [e.horse_number for e in lineup]
    name_by_horse = {e.horse_number: e.princess_name for e in lineup}
    positions = {h: 0.0 for h in horses}
    pace_factors = _init_pace_factors(horses, win_rates)
    velocity = {h: random.uniform(RACE_SPEED_MIN, RACE_SPEED_MAX) * pace_factors[h] for h in horses}
    finish_order: list[int] = []
    ticks: list[RaceTick] = []
    events: list[RaceEvent] = []
    stuck_remaining: dict[int, int] = {}
    surge_remaining: dict[int, int] = {}
    slow_remaining: dict[int, int] = {}
    boost_remaining: dict[int, int] = {}

    for tick in range(1, RACE_TICKS + 1):
        last_event: Optional[RaceEvent] = None
        if len(finish_order) < len(horses):
            ev = _roll_event(lineup)
            if ev is not None:
                events.append(ev)
                last_event = ev
                if ev.kind != "judge":
                    _apply_event(
                        ev,
                        stuck_remaining=stuck_remaining,
                        surge_remaining=surge_remaining,
                        slow_remaining=slow_remaining,
                        boost_remaining=boost_remaining,
                    )

        for horse in horses:
            if horse in finish_order:
                continue
            delta = _tick_delta(
                horse,
                pace_factors=pace_factors,
                velocity=velocity,
                stuck_remaining=stuck_remaining,
                surge_remaining=surge_remaining,
                slow_remaining=slow_remaining,
                boost_remaining=boost_remaining,
            )
            positions[horse] = max(0.0, positions[horse] + delta)
            if positions[horse] >= FINISH_LINE and horse not in finish_order:
                finish_order.append(horse)

        ticks.append(RaceTick(tick=tick, positions=dict(positions), last_event=last_event))
        if len(finish_order) == len(horses):
            break

    if not finish_order:
        finish_order = sorted(horses, key=lambda h: positions[h], reverse=True)

    winner = finish_order[0]
    return RaceResult(
        winner_horse=winner,
        winner_name=name_by_horse[winner],
        finish_order=finish_order,
        ticks=ticks,
        events=events,
    )
