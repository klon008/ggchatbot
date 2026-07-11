"""SQLite CRUD for shared minigames bank."""

from __future__ import annotations

from bot.db import Database

_DEFAULT_BANK = 50_000


async def get_bank(db: Database) -> int:
    row = await db.fetchone("SELECT bank FROM minigames_bank WHERE id = 1")
    if row is None:
        return 0
    return int(row["bank"])


async def add_bank(db: Database, amount: int) -> int:
    await db.execute(
        "UPDATE minigames_bank SET bank = bank + ? WHERE id = 1",
        (amount,),
    )
    return await get_bank(db)


async def set_bank(db: Database, amount: int) -> None:
    await db.execute("UPDATE minigames_bank SET bank = ? WHERE id = 1", (amount,))


async def ensure_row(db: Database, default: int = _DEFAULT_BANK) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO minigames_bank (id, bank) VALUES (1, ?)",
        (default,),
    )
