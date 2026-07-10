"""Персистентность princess-данных в SQLite (data/bot.db)."""
from __future__ import annotations

import re
from typing import Any, Optional

from bot.db import Database
from bot.db import cooldowns as cooldowns_db
from bot.db import daily as daily_db
from bot.db import points as points_db
from bot.db import steal as steal_db
from bot.db import users as users_db

_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PointsStore:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._known_ids: set[str] = set()
        self._pending: dict[str, int] = {}

    async def load(self) -> None:
        self._known_ids = set(await users_db.list_user_ids_with_names(self._db))

    async def flush(self) -> None:
        await self.flush_pending()

    def transfer(self, from_user_id: str, to_user_id: str, amount: int) -> None:
        from_uid = str(from_user_id)
        to_uid = str(to_user_id)
        self._pending[from_uid] = self._pending.get(from_uid, 0) - amount
        self._pending[to_uid] = self._pending.get(to_uid, 0) + amount

    async def flush_pending(self) -> None:
        if not self._pending:
            return
        deltas = dict(self._pending)
        self._pending.clear()
        await points_db.apply_deltas(self._db, deltas)

    async def apply_income_tick(self, eligible_ids: list[str], amount: int) -> None:
        for uid in eligible_ids:
            user_id = str(uid)
            self._pending[user_id] = self._pending.get(user_id, 0) + amount
        await self.flush_pending()

    async def add(self, user_id: str, amount: int) -> int:
        uid = str(user_id)
        self._pending[uid] = self._pending.get(uid, 0) + amount
        return await self.get_balance(uid)

    async def get_balance(self, user_id: str) -> int:
        uid = str(user_id)
        db_balance = await points_db.get_balance(self._db, uid)
        return db_balance + self._pending.get(uid, 0)

    async def set_balance(self, user_id: str, amount: int) -> None:
        uid = str(user_id)
        await points_db.set_balance(self._db, uid, amount)
        self._pending.pop(uid, None)

    def clear_pending(self, user_id: str) -> None:
        self._pending.pop(str(user_id), None)

    async def get_user_entry(self, user_id: str) -> dict[str, int | str] | None:
        uid = str(user_id)
        entry = await points_db.get_user_entry(self._db, uid)
        pending = self._pending.get(uid, 0)
        if entry is None:
            if pending == 0:
                return None
            return {"user_id": uid, "user_name": "", "balance": pending}
        entry["balance"] = int(entry["balance"]) + pending
        return entry

    async def list_entries(self) -> list[dict[str, int | str]]:
        items = await points_db.list_all(self._db)
        seen: set[str] = set()
        for item in items:
            uid = str(item["user_id"])
            seen.add(uid)
            item["balance"] = int(item["balance"]) + self._pending.get(uid, 0)
        for uid, delta in self._pending.items():
            if uid not in seen and delta != 0:
                items.append({"user_id": uid, "user_name": "", "balance": delta})
        return items

    def mark_known(self, user_id: str) -> None:
        self._known_ids.add(str(user_id))

    async def touch_name_if_new(self, user_id: str, user_name: str) -> bool:
        """Записать ник в БД только при первом сообщении пользователя (нет в кэше)."""
        uid = str(user_id)
        if uid in self._known_ids:
            return False
        name = str(user_name).strip()
        if not name:
            return False
        await users_db.touch_user_name(self._db, uid, name)
        self._known_ids.add(uid)
        return True

    async def sync_online_names(self, users: list[dict]) -> tuple[int, int]:
        updated, total = await users_db.sync_online_users(self._db, users)
        for user in users:
            uid = str(user.get("id", ""))
            name = str(user.get("name", "")).strip()
            if uid and name:
                self._known_ids.add(uid)
        return updated, total


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
        points.transfer(thief_id, victim_id, amount)
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
