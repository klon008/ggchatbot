"""Персистентность princess-данных в SQLite (data/bot.db)."""
from __future__ import annotations

import re
from typing import Any, Optional

from bot.db import Database
from bot.db import cooldowns as cooldowns_db
from bot.db import daily as daily_db
from bot.db import steal as steal_db
from bot.economy.points import PointsStore

_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StealStore:
    DEFAULT_INFO = steal_db.DEFAULT_INFO

    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self) -> None:
        return None

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
        await steal_db.record_steal_success(self._db, thief_id, amount)

    async def increment_jail_count(self, user_id: str) -> None:
        await steal_db.increment_jail_count(self._db, user_id)


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
