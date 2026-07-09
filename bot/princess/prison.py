"""Тюрьма: 30 минут, в prison доступна только !срок."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

from bot.db import Database
from bot.db import prison as prison_db

from .settings import MSK, PRISON_DURATION_SEC


class PrisonManager:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def is_in_prison(self, user_id: str) -> bool:
        return await prison_db.is_in_prison(self._db, user_id)

    async def imprison(self, user_id: str) -> None:
        release_time = time.time() + PRISON_DURATION_SEC
        await prison_db.imprison(self._db, user_id, release_time)

    async def get_release_time(self, user_id: str) -> Optional[float]:
        return await prison_db.get_release_time(self._db, user_id)

    async def format_srok(self, user_id: str) -> str:
        release_time = await self.get_release_time(user_id)
        if release_time is None:
            return "Ты не в тюрьме."
        remaining_seconds = release_time - time.time()
        remaining_minutes = int(remaining_seconds // 60) + (1 if remaining_seconds % 60 > 0 else 0)
        release_dt = datetime.fromtimestamp(release_time, tz=MSK)
        release_str = release_dt.strftime("%H:%M")
        return f"Тебе сидеть ещё {remaining_minutes} мин · выход в {release_str} (МСК)"
