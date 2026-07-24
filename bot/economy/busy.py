"""Гейт: во время забега/рулетки/бустера блокирует команды, меняющие баллы."""

from __future__ import annotations

import time

REASON_RACE = "забег"
REASON_ROULETTE = "рулетка"
REASON_BOOSTER = "бустер"

# Команды, которые тратят/начисляют баллы игрокам.
POINT_MUTATING_COMMANDS = frozenset(
    {
        "!дейлик",
        "!дайс",
        "!кража",
        "!списать",
        "!начислить",
        "!бустер",
        "!рулетка",
        "!забег",
        "!опрос",
        "!рыбалка",
        "!заказ",
    }
)

_ALLOW_WHILE_BUSY: dict[str, frozenset[str]] = {
    REASON_RACE: frozenset({"!забег"}),
    REASON_ROULETTE: frozenset({"!рулетка"}),
    # Свой хендлер ответит, если бустер уже открывают.
    REASON_BOOSTER: frozenset({"!бустер"}),
}

_LABELS = {
    REASON_RACE: "забег",
    REASON_ROULETTE: "рулетка",
    REASON_BOOSTER: "открытие бустера",
}

_DENY_COOLDOWN_SEC = 12.0


def _is_read_only_mutating_cmd(cmd: str, text: str) -> bool:
    """Подкоманды без списания баллов (при том же корневом cmd)."""
    if cmd != "!бустер":
        return False
    parts = text.split(maxsplit=1)
    arg = parts[1].strip().lower() if len(parts) > 1 else ""
    return arg == "инфо"


class EconomyBusyGate:
    def __init__(self) -> None:
        self._reasons: set[str] = set()
        self._deny_at: dict[str, float] = {}

    def activate(self, reason: str) -> None:
        self._reasons.add(reason)

    def release(self, reason: str) -> None:
        self._reasons.discard(reason)

    @property
    def is_busy(self) -> bool:
        return bool(self._reasons)

    def current_label(self) -> str:
        for key in (REASON_RACE, REASON_ROULETTE, REASON_BOOSTER):
            if key in self._reasons:
                return _LABELS[key]
        return "мини-игра"

    def should_block(self, cmd: str, text: str = "") -> bool:
        """True — команду нужно отклонить из‑за активного режима."""
        if not self._reasons:
            return False
        if cmd not in POINT_MUTATING_COMMANDS:
            return False
        if _is_read_only_mutating_cmd(cmd, text):
            return False
        for reason in self._reasons:
            if cmd in _ALLOW_WHILE_BUSY.get(reason, frozenset()):
                return False
        return True

    def take_deny_reply(self, user_id: str) -> bool:
        """Антиспам: не чаще раза в _DENY_COOLDOWN_SEC на пользователя."""
        now = time.monotonic()
        uid = str(user_id)
        last = self._deny_at.get(uid, 0.0)
        if now - last < _DENY_COOLDOWN_SEC:
            return False
        self._deny_at[uid] = now
        if len(self._deny_at) > 200:
            cutoff = now - _DENY_COOLDOWN_SEC
            self._deny_at = {k: v for k, v in self._deny_at.items() if v >= cutoff}
        return True

    def deny_message(self, user_name: str) -> str:
        return (
            f"{user_name}, сейчас идёт {self.current_label()} — "
            "команды с баллами временно недоступны."
        )
