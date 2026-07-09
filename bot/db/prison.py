"""Prison persistence."""

from __future__ import annotations

import time
from typing import Optional

from .connection import Database


async def is_in_prison(db: Database, user_id: str) -> bool:
    uid = str(user_id)
    row = await db.fetchone(
        "SELECT release_time FROM prison WHERE user_id = ?",
        (uid,),
    )
    if row is None:
        return False
    release_time = float(row["release_time"])
    if time.time() < release_time:
        return True
    await db.execute("DELETE FROM prison WHERE user_id = ?", (uid,))
    return False


async def imprison(db: Database, user_id: str, release_time: float) -> None:
    uid = str(user_id)
    await db.execute(
        "INSERT INTO prison (user_id, release_time) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET release_time = excluded.release_time",
        (uid, release_time),
    )


async def get_release_time(db: Database, user_id: str) -> Optional[float]:
    uid = str(user_id)
    row = await db.fetchone(
        "SELECT release_time FROM prison WHERE user_id = ?",
        (uid,),
    )
    if row is None:
        return None
    release_time = float(row["release_time"])
    if time.time() >= release_time:
        await db.execute("DELETE FROM prison WHERE user_id = ?", (uid,))
        return None
    return release_time
