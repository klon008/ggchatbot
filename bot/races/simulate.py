"""Симуляция забега: одинаковый темп, разброс только от boost / slow / stun."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from bot.db.races import LineupEntry
from . import settings as _cfg

FINISH_LINE = float(getattr(_cfg, "FINISH_LINE", 375.0))
RACE_EVENT_CHANCE = float(getattr(_cfg, "RACE_EVENT_CHANCE", 0.12))
RACE_SPEED_BASE = float(getattr(_cfg, "RACE_SPEED_BASE", 2.5))
RACE_TICKS = int(getattr(_cfg, "RACE_TICKS", 220))
RACE_EVENTS_AFTER_FRAC = float(getattr(_cfg, "RACE_EVENTS_AFTER_FRAC", 0.08))
STUMBLE_STUCK_MAX = int(getattr(_cfg, "STUMBLE_STUCK_MAX", 8))
STUMBLE_STUCK_MIN = int(getattr(_cfg, "STUMBLE_STUCK_MIN", 3))
BOOST_TICKS_MIN = int(getattr(_cfg, "BOOST_TICKS_MIN", 4))
BOOST_TICKS_MAX = int(getattr(_cfg, "BOOST_TICKS_MAX", 7))
SLOW_TICKS_MIN = int(getattr(_cfg, "SLOW_TICKS_MIN", 4))
SLOW_TICKS_MAX = int(getattr(_cfg, "SLOW_TICKS_MAX", 6))
BOOST_MULT = float(getattr(_cfg, "BOOST_MULT", 1.65))
SLOW_MULT = float(getattr(_cfg, "SLOW_MULT", 0.45))

STATUS_NORMAL = "normal"
STATUS_BOOST = "boost"
STATUS_SLOW = "slow"
STATUS_STUN = "stun"

KIND_BOOST = "boost"
KIND_SLOW = "slow"
KIND_STUN = "stun"

_EVENT_KINDS = (KIND_BOOST, KIND_SLOW, KIND_STUN)


@dataclass
class RaceEvent:
    horse_number: int
    princess_name: str
    kind: str


@dataclass
class RaceTick:
    tick: int
    positions: dict[int, float]
    statuses: dict[int, str] = field(default_factory=dict)
    last_event: Optional[RaceEvent] = None


@dataclass
class RaceResult:
    winner_horse: int
    winner_name: str
    finish_order: list[int]
    ticks: list[RaceTick] = field(default_factory=list)
    events: list[RaceEvent] = field(default_factory=list)


def _roll_event(lineup: list[LineupEntry]) -> Optional[RaceEvent]:
    if random.random() > RACE_EVENT_CHANCE:
        return None
    entry = random.choice(lineup)
    return RaceEvent(entry.horse_number, entry.princess_name, random.choice(_EVENT_KINDS))


def _apply_event(
    ev: RaceEvent,
    *,
    stuck_remaining: dict[int, int],
    boost_remaining: dict[int, int],
    slow_remaining: dict[int, int],
) -> None:
    horse = ev.horse_number
    if ev.kind == KIND_STUN:
        stuck_remaining[horse] = max(
            stuck_remaining.get(horse, 0),
            random.randint(STUMBLE_STUCK_MIN, STUMBLE_STUCK_MAX),
        )
    elif ev.kind == KIND_SLOW:
        slow_remaining[horse] = max(
            slow_remaining.get(horse, 0),
            random.randint(SLOW_TICKS_MIN, SLOW_TICKS_MAX),
        )
    elif ev.kind == KIND_BOOST:
        boost_remaining[horse] = max(
            boost_remaining.get(horse, 0),
            random.randint(BOOST_TICKS_MIN, BOOST_TICKS_MAX),
        )


def _status_for_horse(
    horse: int,
    *,
    stuck_remaining: dict[int, int],
    boost_remaining: dict[int, int],
    slow_remaining: dict[int, int],
) -> str:
    if stuck_remaining.get(horse, 0) > 0:
        return STATUS_STUN
    if boost_remaining.get(horse, 0) > 0:
        return STATUS_BOOST
    if slow_remaining.get(horse, 0) > 0:
        return STATUS_SLOW
    return STATUS_NORMAL


def _tick_delta(
    horse: int,
    *,
    stuck_remaining: dict[int, int],
    boost_remaining: dict[int, int],
    slow_remaining: dict[int, int],
) -> float:
    """Одинаковая база; множители только от статусов."""
    if stuck_remaining.get(horse, 0) > 0:
        stuck_remaining[horse] -= 1
        return 0.0

    delta = RACE_SPEED_BASE

    if boost_remaining.get(horse, 0) > 0:
        boost_remaining[horse] -= 1
        delta *= BOOST_MULT
    if slow_remaining.get(horse, 0) > 0:
        slow_remaining[horse] -= 1
        delta *= SLOW_MULT

    return delta


def _complete_finish_order(
    finish_order: list[int],
    horses: list[int],
    positions: dict[int, float],
) -> list[int]:
    order = list(finish_order)
    finished = set(order)
    rest = [h for h in horses if h not in finished]
    rest.sort(key=lambda h: positions.get(h, 0.0), reverse=True)
    order.extend(rest)
    return order


def simulate_race(
    lineup: list[LineupEntry],
    win_rates: Optional[dict[int, float]] = None,  # noqa: ARG001 — только для odds, не для бега
) -> RaceResult:
    horses = [e.horse_number for e in lineup]
    name_by_horse = {e.horse_number: e.princess_name for e in lineup}
    positions = {h: 0.0 for h in horses}

    finish_order: list[int] = []
    ticks: list[RaceTick] = []
    events: list[RaceEvent] = []
    stuck_remaining: dict[int, int] = {}
    boost_remaining: dict[int, int] = {}
    slow_remaining: dict[int, int] = {}

    events_after = FINISH_LINE * max(0.0, min(0.5, RACE_EVENTS_AFTER_FRAC))

    for tick in range(1, RACE_TICKS + 1):
        last_event: Optional[RaceEvent] = None
        leader_pos = max(positions.values()) if positions else 0.0

        if len(finish_order) < len(horses) and leader_pos >= events_after:
            ev = _roll_event(lineup)
            if ev is not None:
                events.append(ev)
                last_event = ev
                _apply_event(
                    ev,
                    stuck_remaining=stuck_remaining,
                    boost_remaining=boost_remaining,
                    slow_remaining=slow_remaining,
                )

        statuses = {
            h: _status_for_horse(
                h,
                stuck_remaining=stuck_remaining,
                boost_remaining=boost_remaining,
                slow_remaining=slow_remaining,
            )
            for h in horses
        }

        for horse in horses:
            if horse in finish_order:
                positions[horse] = FINISH_LINE
                continue
            delta = _tick_delta(
                horse,
                stuck_remaining=stuck_remaining,
                boost_remaining=boost_remaining,
                slow_remaining=slow_remaining,
            )
            positions[horse] = max(0.0, positions[horse] + delta)
            if positions[horse] >= FINISH_LINE and horse not in finish_order:
                positions[horse] = FINISH_LINE
                finish_order.append(horse)

        ticks.append(
            RaceTick(
                tick=tick,
                positions=dict(positions),
                statuses=statuses,
                last_event=last_event,
            )
        )
        if len(finish_order) == len(horses):
            break

    # Порядок для выплат: кто не добежал — по дистанции (без телепорта к финишу)
    finish_order = _complete_finish_order(finish_order, horses, positions)

    winner = finish_order[0]
    return RaceResult(
        winner_horse=winner,
        winner_name=name_by_horse[winner],
        finish_order=finish_order,
        ticks=ticks,
        events=events,
    )


def build_obs_script(
    result: RaceResult,
    lineup: list[LineupEntry],
    *,
    display_sec: float,
    finish_line: float = FINISH_LINE,
) -> dict:
    """Сценарий для OBS: равномерное время по тикам (без замедления хвоста после лидера)."""
    ticks = result.ticks
    if not ticks:
        return {
            "durationSec": 0.5,
            "finishLine": finish_line,
            "finishOrder": list(result.finish_order),
            "winnerHorse": result.winner_horse,
            "winnerName": result.winner_name,
            "keyframes": [],
            "lineup": [
                {"horse_number": e.horse_number, "princess_name": e.princess_name}
                for e in lineup
            ],
        }

    last_idx = len(ticks) - 1

    keyframes: list[dict] = []
    for i, tick in enumerate(ticks):
        if i > last_idx:
            break
        # Только cap у линии — без телепорта всех к финишу на последнем кадре
        positions = {
            str(k): round(min(float(v), finish_line), 2)
            for k, v in tick.positions.items()
        }
        t = 0.0 if last_idx <= 0 else display_sec * (i / last_idx)
        keyframes.append({
            "t": round(t, 3),
            "positions": positions,
            "statuses": {str(k): v for k, v in tick.statuses.items()},
        })

    duration = round(display_sec, 3)
    if keyframes:
        keyframes[-1]["t"] = duration

    return {
        "durationSec": duration,
        "finishLine": finish_line,
        "finishOrder": list(result.finish_order),
        "winnerHorse": result.winner_horse,
        "winnerName": result.winner_name,
        "keyframes": keyframes,
        "lineup": [
            {
                "horse_number": e.horse_number,
                "princess_name": e.princess_name,
            }
            for e in lineup
        ],
    }
