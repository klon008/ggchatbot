"""Конфиг расписания ивентов принцесс (множители за просмотр и сообщения)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from .economy import now_msk

# Дефолт: просмотр — понедельник (0), сообщения — вторник (1), x2, включено.
DEFAULT_VIEW_ENABLED = True
DEFAULT_VIEW_WEEKDAYS = (0,)
DEFAULT_VIEW_MULT = 2.0
DEFAULT_MESSAGE_ENABLED = True
DEFAULT_MESSAGE_WEEKDAYS = (1,)
DEFAULT_MESSAGE_MULT = 2.0

GRANT_ITEMS = ("view_boost", "message_boost")
GRANT_ITEM_TO_KIND = {
    "view_boost": "view",
    "message_boost": "message",
}


def today_key() -> str:
    return now_msk().strftime("%Y-%m-%d")


def scaled_points(base: int, mult: float) -> int:
    # half-up: Python round() банковский (4.5 → 4), для наград не подходит.
    return max(1, int(int(base) * float(mult) + 0.5))


def format_mult(mult: float) -> str:
    value = float(mult)
    if value.is_integer():
        return f"x{int(value)}"
    return f"x{value:g}"


@dataclass
class PrincessEventsConfig:
    view_enabled: bool
    view_weekdays: list[int]
    view_mult: float
    message_enabled: bool
    message_weekdays: list[int]
    message_mult: float

    @classmethod
    def defaults(cls) -> "PrincessEventsConfig":
        return cls(
            view_enabled=DEFAULT_VIEW_ENABLED,
            view_weekdays=list(DEFAULT_VIEW_WEEKDAYS),
            view_mult=DEFAULT_VIEW_MULT,
            message_enabled=DEFAULT_MESSAGE_ENABLED,
            message_weekdays=list(DEFAULT_MESSAGE_WEEKDAYS),
            message_mult=DEFAULT_MESSAGE_MULT,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_view_active_today(self) -> bool:
        if not self.view_enabled:
            return False
        return now_msk().weekday() in self.view_weekdays

    def is_message_active_today(self) -> bool:
        if not self.message_enabled:
            return False
        return now_msk().weekday() in self.message_weekdays


def _parse_weekdays(raw: Any, field: str) -> list[int]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError(field)
    parsed: list[int] = []
    for w in raw:
        try:
            day = int(w)
        except (TypeError, ValueError) as exc:
            raise ValueError(field) from exc
        if day < 0 or day > 6:
            raise ValueError(field)
        if day not in parsed:
            parsed.append(day)
    return sorted(parsed)


def _parse_mult(raw: Any, field: str) -> float:
    try:
        n = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(field) from exc
    if n < 1:
        raise ValueError(field)
    return n


def parse_events_override(raw: Optional[dict[str, Any]]) -> PrincessEventsConfig:
    base = PrincessEventsConfig.defaults()
    if not raw or not isinstance(raw, dict):
        return base
    enabled = raw.get("view_enabled")
    if enabled is not None:
        base.view_enabled = bool(enabled)
    weekdays = raw.get("view_weekdays")
    if weekdays is not None:
        base.view_weekdays = _parse_weekdays(weekdays, "view_weekdays")
    mult = raw.get("view_mult")
    if mult is not None:
        base.view_mult = _parse_mult(mult, "view_mult")
    enabled = raw.get("message_enabled")
    if enabled is not None:
        base.message_enabled = bool(enabled)
    weekdays = raw.get("message_weekdays")
    if weekdays is not None:
        base.message_weekdays = _parse_weekdays(weekdays, "message_weekdays")
    mult = raw.get("message_mult")
    if mult is not None:
        base.message_mult = _parse_mult(mult, "message_mult")
    return base


def validate_events_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload")
    cfg = parse_events_override(payload)
    return cfg.to_dict()
