"""Points balance CRUD."""

from __future__ import annotations

from .connection import Database


async def ensure_user(db: Database, user_id: str) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO points (user_id, balance) VALUES (?, 0)",
        (str(user_id),),
    )


async def get_balance(db: Database, user_id: str) -> int:
    row = await db.fetchone(
        "SELECT balance FROM points WHERE user_id = ?",
        (str(user_id),),
    )
    return int(row["balance"]) if row else 0


async def add_balance(db: Database, user_id: str, amount: int) -> int:
    uid = str(user_id)
    await ensure_user(db, uid)
    await db.execute(
        "UPDATE points SET balance = balance + ? WHERE user_id = ?",
        (amount, uid),
    )
    return await get_balance(db, uid)


async def set_balance(db: Database, user_id: str, amount: int) -> None:
    uid = str(user_id)
    await ensure_user(db, uid)
    await db.execute(
        "UPDATE points SET balance = ? WHERE user_id = ?",
        (max(0, amount), uid),
    )


async def transfer_balance(
    db: Database,
    from_user_id: str,
    to_user_id: str,
    amount: int,
) -> None:
    """Atomically move points between users (caller must be inside transaction)."""
    conn = db.conn
    from_uid = str(from_user_id)
    to_uid = str(to_user_id)
    await conn.execute(
        "INSERT OR IGNORE INTO points (user_id, balance) VALUES (?, 0)",
        (from_uid,),
    )
    await conn.execute(
        "INSERT OR IGNORE INTO points (user_id, balance) VALUES (?, 0)",
        (to_uid,),
    )
    await conn.execute(
        "UPDATE points SET balance = balance - ? WHERE user_id = ?",
        (amount, from_uid),
    )
    await conn.execute(
        "UPDATE points SET balance = balance + ? WHERE user_id = ?",
        (amount, to_uid),
    )
