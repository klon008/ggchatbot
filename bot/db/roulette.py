"""SQLite CRUD for roulette_meta and roulette_bets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from bot.db import Database


@dataclass
class RouletteMeta:
    auto_enabled: bool
    state: str
    round_id: int
    round_opened_at: Optional[float]
    closes_at: Optional[float]
    cooldown_until: Optional[float]
    collect_sec: int
    cooldown_sec: int
    last_result: Optional[dict[str, Any]]


@dataclass
class RouletteBet:
    round_id: int
    user_id: str
    user_name: str
    amount: int
    bet_type: str
    bet_payload: dict[str, Any]


def _row_to_meta(row) -> RouletteMeta:
    last_raw = row["last_result"]
    last_result = None
    if last_raw:
        try:
            last_result = json.loads(last_raw)
        except json.JSONDecodeError:
            last_result = None
    return RouletteMeta(
        auto_enabled=bool(row["auto_enabled"]),
        state=str(row["state"]),
        round_id=int(row["round_id"]),
        round_opened_at=row["round_opened_at"],
        closes_at=row["closes_at"],
        cooldown_until=row["cooldown_until"],
        collect_sec=int(row["collect_sec"]),
        cooldown_sec=int(row["cooldown_sec"]),
        last_result=last_result,
    )


def _row_to_bet(row) -> RouletteBet:
    return RouletteBet(
        round_id=int(row["round_id"]),
        user_id=str(row["user_id"]),
        user_name=str(row["user_name"]),
        amount=int(row["amount"]),
        bet_type=str(row["bet_type"]),
        bet_payload=json.loads(row["bet_payload"]),
    )


async def get_meta(db: Database) -> RouletteMeta:
    row = await db.fetchone("SELECT * FROM roulette_meta WHERE id = 1")
    if row is None:
        raise RuntimeError("roulette_meta row missing")
    return _row_to_meta(row)


async def update_meta(db: Database, **fields: Any) -> None:
    if not fields:
        return
    if "last_result" in fields and fields["last_result"] is not None:
        fields["last_result"] = json.dumps(fields["last_result"], ensure_ascii=False)
    if "auto_enabled" in fields:
        fields["auto_enabled"] = 1 if fields["auto_enabled"] else 0
    cols = ", ".join(f"{k} = ?" for k in fields)
    params = tuple(fields.values())
    await db.execute(f"UPDATE roulette_meta SET {cols} WHERE id = 1", params)


async def has_bet(db: Database, round_id: int, user_id: str) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM roulette_bets WHERE round_id = ? AND user_id = ?",
        (round_id, str(user_id)),
    )
    return row is not None


async def add_bet(db: Database, bet: RouletteBet) -> None:
    await db.execute(
        """
        INSERT INTO roulette_bets (
            round_id, user_id, user_name, amount, bet_type, bet_payload
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            bet.round_id,
            bet.user_id,
            bet.user_name,
            bet.amount,
            bet.bet_type,
            json.dumps(bet.bet_payload, ensure_ascii=False),
        ),
    )


async def list_bets(db: Database, round_id: int) -> list[RouletteBet]:
    rows = await db.fetchall(
        """
        SELECT * FROM roulette_bets
        WHERE round_id = ?
        ORDER BY id
        """,
        (round_id,),
    )
    return [_row_to_bet(row) for row in rows]


async def delete_bets(db: Database, round_id: int) -> None:
    await db.execute("DELETE FROM roulette_bets WHERE round_id = ?", (round_id,))
