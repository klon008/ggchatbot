"""Points balance CRUD."""

from __future__ import annotations

from .connection import Database


async def ensure_user(db: Database, user_id: str) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO points (user_id, balance) VALUES (?, 0)",
        (str(user_id),),
    )


async def list_all(db: Database) -> list[dict[str, int | str]]:
    rows = await db.fetchall(
        """
        SELECT p.user_id,
               COALESCE(u.user_name, '') AS user_name,
               p.balance
        FROM points p
        LEFT JOIN user_names u ON u.user_id = p.user_id
        ORDER BY p.balance DESC, p.user_id ASC
        """
    )
    return [
        {
            "user_id": row["user_id"],
            "user_name": row["user_name"],
            "balance": int(row["balance"]),
        }
        for row in rows
    ]


async def get_user_entry(db: Database, user_id: str) -> dict[str, int | str] | None:
    row = await db.fetchone(
        """
        SELECT p.user_id,
               COALESCE(u.user_name, '') AS user_name,
               p.balance
        FROM points p
        LEFT JOIN user_names u ON u.user_id = p.user_id
        WHERE p.user_id = ?
        """,
        (str(user_id),),
    )
    if row is None:
        return None
    return {
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "balance": int(row["balance"]),
    }


async def delete_user(db: Database, user_id: str) -> bool:
    cursor = await db.execute(
        "DELETE FROM points WHERE user_id = ?",
        (str(user_id),),
    )
    return cursor.rowcount > 0


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
