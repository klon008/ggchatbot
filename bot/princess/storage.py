"""Персистентность princess-данных в SQLite (data/bot.db)."""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from bot.db import Database
from bot.db import cooldowns as cooldowns_db
from bot.db import daily as daily_db
from bot.db import minigames_bank
from bot.db import steal as steal_db
from bot.db import steal_meta as steal_meta_db
from bot.economy.points import PointsStore

from .economy import is_steal_schedule_day, now_msk
from .settings import STEAL_ALLOWED_WEEKDAYS

_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_WEEKDAY_RU = {
    0: "понедельник",
    1: "вторник",
    2: "среда",
    3: "четверг",
    4: "пятница",
    5: "суббота",
    6: "воскресенье",
}


def next_steal_weekday_label() -> str:
    now = now_msk()
    for i in range(1, 8):
        day = (now.weekday() + i) % 7
        if day in STEAL_ALLOWED_WEEKDAYS:
            return _WEEKDAY_RU[day]
    return "среда"


class StealStore:
    DEFAULT_INFO = steal_db.DEFAULT_INFO

    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self) -> None:
        await steal_meta_db.ensure_meta(self._db)

    async def flush(self) -> None:
        return None

    async def get_info(self, user_id: str) -> dict:
        return await steal_db.get_info(self._db, user_id)

    def mutate_info(self, user_id: str) -> "_StealMutator":
        return _StealMutator(self._db, str(user_id))

    async def execute_steal(
        self,
        points: PointsStore,
        thief_id: str,
        victim_id: str,
        amount: int,
    ) -> None:
        points.transfer(victim_id, thief_id, amount)
        await points.flush_pending()
        await steal_db.record_steal_success(self._db, thief_id, amount)

    async def execute_bank_steal(
        self,
        points: PointsStore,
        thief_id: str,
        amount: int,
        *,
        min_required: int,
    ) -> Optional[int]:
        """Steal from minigames_bank. Returns taken amount or None on failure."""
        if amount <= 0 or min_required <= 0:
            return None
        bank = await minigames_bank.get_bank(self._db)
        if bank < min_required:
            return None
        take = min(amount, bank)
        if not await minigames_bank.try_withdraw(self._db, take):
            return None
        await points.add(thief_id, take)
        await points.flush_pending()
        await steal_db.record_steal_success(self._db, thief_id, take)
        return take

    async def increment_jail_count(self, user_id: str) -> None:
        await steal_db.increment_jail_count(self._db, user_id)

    async def get_meta(self) -> dict[str, Any]:
        return await steal_meta_db.get_meta(self._db)

    async def is_allowed(self) -> bool:
        if is_steal_schedule_day():
            return True
        meta = await self.get_meta()
        if meta["override_enabled"]:
            return True
        until = meta["override_until"]
        if until is not None and time.time() < until:
            return True
        return False

    async def get_status(self) -> dict[str, Any]:
        meta = await self.get_meta()
        now = time.time()
        until = meta["override_until"]
        if until is not None and until <= now:
            until = None
        schedule_allowed = is_steal_schedule_day()
        override_active = bool(meta["override_enabled"] or (until is not None and until > now))
        return {
            "schedule_allowed": schedule_allowed,
            "override_enabled": bool(meta["override_enabled"]),
            "override_until": until,
            "effective_allowed": schedule_allowed or override_active,
            "schedule_weekdays": list(STEAL_ALLOWED_WEEKDAYS),
            "now_msk": now_msk().isoformat(),
            "next_steal_day": next_steal_weekday_label(),
        }

    async def set_override(
        self,
        *,
        enabled: bool = False,
        until: Optional[float] = None,
    ) -> dict[str, Any]:
        return await steal_meta_db.set_meta(
            self._db,
            override_enabled=enabled,
            override_until=until,
        )

    async def clear_override(self) -> dict[str, Any]:
        return await steal_meta_db.set_meta(
            self._db,
            override_enabled=False,
            override_until=None,
        )

    async def set_schedule_open_key(self, key: str) -> None:
        await steal_meta_db.set_meta(self._db, last_schedule_open_key=key)

    async def clear_expired_timer(self) -> bool:
        """Clear override_until if expired. Returns True if cleared."""
        meta = await self.get_meta()
        until = meta["override_until"]
        if until is None or until > time.time():
            return False
        await steal_meta_db.set_meta(self._db, override_until=None)
        return True

class _StealMutator:
    def __init__(self, db: Database, user_id: str) -> None:
        self._db = db
        self._user_id = user_id
        self._info: Optional[dict] = None

    async def __aenter__(self) -> dict:
        self._info = await steal_db.get_info(self._db, self._user_id)
        return self._info

    async def __aexit__(self, *args: object) -> None:
        if self._info is not None:
            await steal_db.save_info(self._db, self._user_id, self._info)


class DailyStore:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._today_str = ""

    async def load(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def normalize(self) -> None:
        return None

    def mutate(self) -> "_DailyMutator":
        from .economy import now_msk

        self._today_str = now_msk().strftime("%Y-%m-%d")
        return _DailyMutator(self._db, self._today_str)


class _DailyMutator:
    def __init__(self, db: Database, today_str: str) -> None:
        self._db = db
        self._today_str = today_str
        self._data: Optional[dict[str, Any]] = None

    async def __aenter__(self) -> dict[str, Any]:
        self._data = await daily_db.build_mutate_snapshot(self._db, self._today_str)
        return self._data

    async def __aexit__(self, *args: object) -> None:
        if self._data is None:
            return
        await daily_db.persist_mutate_snapshot(self._db, self._data, self._today_str)
        for key, value in self._data.items():
            if key == self._today_str or not _DATE_KEY.match(key):
                continue
            if isinstance(value, list):
                await daily_db.save_claims_for_day(self._db, key, value)


class DiceCooldownStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_last(self, user_id: str) -> float:
        return await cooldowns_db.get_last(self._db, user_id)

    async def set_last(self, user_id: str, last_time: float) -> None:
        await cooldowns_db.set_last(self._db, user_id, last_time)
