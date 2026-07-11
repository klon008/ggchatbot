"""Симуляция забега с событиями."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from bot.db.races import LineupEntry

from .settings import FINISH_LINE, RACE_EVENT_CHANCE, RACE_TICKS


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
    ("second_wind", "Открылось второе дыхание!", 1.8, 3),
    ("stumble", "Споткнулась и упала!", 0.0, 2),
    ("shortcut", "Срезала угол!", 1.4, 2),
    ("tangle", "Запуталась в гриве!", 0.6, 2),
    ("cheer", "Фанаты подбадривают!", 1.2, 2),
]

_FLAVOR_MESSAGES = [
    "Судья следит за чистотой заезда!",
    "Кто-то машет флажком!",
    "Трибуны гудят!",
]


def _roll_event(lineup: list[LineupEntry]) -> Optional[RaceEvent]:
    if random.random() > RACE_EVENT_CHANCE:
        return None
    entry = random.choice(lineup)
    if random.random() < 0.25:
        return RaceEvent(entry.horse_number, entry.princess_name, "judge", random.choice(_FLAVOR_MESSAGES))
    kind, msg, _, _ = random.choice(_MECHANICAL_EVENTS)
    return RaceEvent(entry.horse_number, entry.princess_name, kind, msg)


def _speed_modifier(event: RaceEvent, boost_remaining: dict[int, int]) -> float:
    horse = event.horse_number
    if event.kind == "second_wind":
        boost_remaining[horse] = boost_remaining.get(horse, 0) + 3
        return 1.8
    if event.kind == "stumble":
        boost_remaining[horse] = boost_remaining.get(horse, 0) + 2
        return 0.0
    if event.kind == "shortcut":
        boost_remaining[horse] = boost_remaining.get(horse, 0) + 2
        return 1.4
    if event.kind == "tangle":
        boost_remaining[horse] = boost_remaining.get(horse, 0) + 2
        return 0.6
    if event.kind == "cheer":
        boost_remaining[horse] = boost_remaining.get(horse, 0) + 2
        return 1.2
    return 1.0


def simulate_race(lineup: list[LineupEntry]) -> RaceResult:
    horses = [e.horse_number for e in lineup]
    name_by_horse = {e.horse_number: e.princess_name for e in lineup}
    positions = {h: 0.0 for h in horses}
    finish_order: list[int] = []
    ticks: list[RaceTick] = []
    events: list[RaceEvent] = []
    boost_remaining: dict[int, int] = {}
    active_event: Optional[RaceEvent] = None

    for tick in range(1, RACE_TICKS + 1):
        last_event: Optional[RaceEvent] = None
        if len(finish_order) < len(horses):
            ev = _roll_event(lineup)
            if ev is not None:
                events.append(ev)
                last_event = ev
                if ev.kind != "judge":
                    active_event = ev
                    _speed_modifier(ev, boost_remaining)

        for horse in horses:
            if horse in finish_order:
                continue
            base = random.uniform(1.5, 3.5)
            if boost_remaining.get(horse, 0) > 0:
                base *= 1.5
                boost_remaining[horse] -= 1
            if active_event and active_event.horse_number == horse:
                mod = _speed_modifier(active_event, boost_remaining)
                if mod == 0.0:
                    base = -random.uniform(2.0, 5.0)
                else:
                    base *= mod
            positions[horse] = max(0.0, positions[horse] + base)
            if positions[horse] >= FINISH_LINE and horse not in finish_order:
                finish_order.append(horse)

        ticks.append(RaceTick(tick=tick, positions=dict(positions), last_event=last_event))
        active_event = None
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
