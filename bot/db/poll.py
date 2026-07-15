"""SQLite CRUD for poll_meta and poll_bets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from bot.db import Database


@dataclass
class PollMeta:
    state: str
    round_id: int
    title: str
    options: list[str]
    round_opened_at: Optional[float]
    closes_at: Optional[float]
    collect_sec: int
    winning_option: Optional[int]
    last_result: Optional[dict[str, Any]]


@dataclass
class PollBet:
    round_id: int
    user_id: str
    user_name: str
    amount: int
    option_index: int


def _parse_options(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]


def _parse_last_result(raw: Any) -> Optional[dict[str, Any]]:
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _row_to_meta(row) -> PollMeta:
    winning = row["winning_option"]
    return PollMeta(
        state=str(row["state"]),
        round_id=int(row["round_id"]),
        title=str(row["title"] or ""),
        options=_parse_options(row["options"]),
        round_opened_at=row["round_opened_at"],
        closes_at=row["closes_at"],
        collect_sec=int(row["collect_sec"]),
        winning_option=int(winning) if winning is not None else None,
        last_result=_parse_last_result(row["last_result"]),
    )


def _row_to_bet(row) -> PollBet:
    return PollBet(
        round_id=int(row["round_id"]),
        user_id=str(row["user_id"]),
        user_name=str(row["user_name"]),
        amount=int(row["amount"]),
        option_index=int(row["option_index"]),
    )


async def get_meta(db: Database) -> PollMeta:
    row = await db.fetchone("SELECT * FROM poll_meta WHERE id = 1")
    if row is None:
        raise RuntimeError("poll_meta row missing")
    return _row_to_meta(row)


async def update_meta(db: Database, **fields: Any) -> None:
    if not fields:
        return
    if "options" in fields and fields["options"] is not None:
        fields["options"] = json.dumps(fields["options"], ensure_ascii=False)
    if "last_result" in fields and fields["last_result"] is not None:
        fields["last_result"] = json.dumps(fields["last_result"], ensure_ascii=False)
    cols = ", ".join(f"{k} = ?" for k in fields)
    params = tuple(fields.values())
    await db.execute(f"UPDATE poll_meta SET {cols} WHERE id = 1", params)


async def get_bet(db: Database, round_id: int, user_id: str) -> Optional[PollBet]:
    row = await db.fetchone(
        "SELECT * FROM poll_bets WHERE round_id = ? AND user_id = ?",
        (round_id, str(user_id)),
    )
    if row is None:
        return None
    return _row_to_bet(row)


async def add_bet(db: Database, bet: PollBet) -> None:
    await db.execute(
        """
        INSERT INTO poll_bets (
            round_id, user_id, user_name, amount, option_index
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            bet.round_id,
            bet.user_id,
            bet.user_name,
            bet.amount,
            bet.option_index,
        ),
    )


async def add_to_bet(
    db: Database,
    round_id: int,
    user_id: str,
    extra_amount: int,
    user_name: str,
) -> None:
    await db.execute(
        """
        UPDATE poll_bets
        SET amount = amount + ?, user_name = ?
        WHERE round_id = ? AND user_id = ?
        """,
        (extra_amount, user_name, round_id, str(user_id)),
    )


async def list_bets(db: Database, round_id: int) -> list[PollBet]:
    rows = await db.fetchall(
        """
        SELECT * FROM poll_bets
        WHERE round_id = ?
        ORDER BY id
        """,
        (round_id,),
    )
    return [_row_to_bet(row) for row in rows]


async def delete_bets(db: Database, round_id: int) -> None:
    await db.execute("DELETE FROM poll_bets WHERE round_id = ?", (round_id,))
