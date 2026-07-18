"""Хранилище балансов принцесс с pending-кэшем."""
from __future__ import annotations

from bot.db import Database
from bot.db import points as points_db
from bot.db import users as users_db


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

    async def touch_name(self, user_id: str, user_name: str) -> None:
        """Upsert ника в user_names на каждое сообщение (актуальный lookup !альбом)."""
        uid = str(user_id)
        name = str(user_name).strip()
        if not name:
            return
        await users_db.touch_user_name(self._db, uid, name)
        self._known_ids.add(uid)

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
