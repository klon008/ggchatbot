"""Конфиг расписания ивентов рыбалки (рыбный день / буст клёва)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from .economy import now_msk

# Дефолт: четверг (weekday=3), 30 зарядов, включено.
DEFAULT_BOOST_ENABLED = True
DEFAULT_BOOST_WEEKDAYS = (3,)
DEFAULT_BOOST_CASTS = 30

GRANT_ITEMS = ("mermaid_shield", "bite_boost", "steal_safe")


@dataclass
class FishingEventsConfig:
    boost_enabled: bool
    boost_weekdays: list[int]
    boost_casts: int

    @classmethod
    def defaults(cls) -> "FishingEventsConfig":
        return cls(
            boost_enabled=DEFAULT_BOOST_ENABLED,
            boost_weekdays=list(DEFAULT_BOOST_WEEKDAYS),
            boost_casts=DEFAULT_BOOST_CASTS,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_active_today(self) -> bool:
        if not self.boost_enabled:
            return False
        return now_msk().weekday() in self.boost_weekdays


def parse_events_override(raw: Optional[dict[str, Any]]) -> FishingEventsConfig:
    base = FishingEventsConfig.defaults()
    if not raw or not isinstance(raw, dict):
        return base
    enabled = raw.get("boost_enabled")
    if enabled is not None:
        base.boost_enabled = bool(enabled)
    weekdays = raw.get("boost_weekdays")
    if weekdays is not None:
        if not isinstance(weekdays, (list, tuple)):
            raise ValueError("boost_weekdays")
        parsed: list[int] = []
        for w in weekdays:
            try:
                day = int(w)
            except (TypeError, ValueError) as exc:
                raise ValueError("boost_weekdays") from exc
            if day < 0 or day > 6:
                raise ValueError("boost_weekdays")
            if day not in parsed:
                parsed.append(day)
        base.boost_weekdays = sorted(parsed)
    casts = raw.get("boost_casts")
    if casts is not None:
        try:
            n = int(casts)
        except (TypeError, ValueError) as exc:
            raise ValueError("boost_casts") from exc
        if n < 0:
            raise ValueError("boost_casts")
        base.boost_casts = n
    return base


def validate_events_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload")
    cfg = parse_events_override(payload)
    return cfg.to_dict()
