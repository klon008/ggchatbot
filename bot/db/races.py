"""SQLite CRUD for races tables."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from bot.db import Database


@dataclass
class RacesMeta:
    auto_enabled: bool
    state: str
    round_id: int
    round_opened_at: Optional[float]
    closes_at: Optional[float]
    cooldown_until: Optional[float]
    collect_sec: int
    cooldown_sec: int
    race_delay_sec: int
    last_result: Optional[dict[str, Any]]
    race_progress: Optional[dict[str, Any]]
    fixed_odds: Optional[dict[str, float]]


@dataclass
class RacesBet:
    round_id: int
    user_id: str
    user_name: str
    amount: int
    horse_number: int


@dataclass
class LineupEntry:
    horse_number: int
    princess_name: str


@dataclass
class PrincessStats:
    princess_name: str
    races_count: int
    wins_count: int


def _parse_json(raw: Any) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _row_to_meta(row) -> RacesMeta:
    fixed_odds_raw = _parse_json(row["fixed_odds"])
    fixed_odds = None
    if fixed_odds_raw:
        fixed_odds = {str(k): float(v) for k, v in fixed_odds_raw.items()}
    return RacesMeta(
        auto_enabled=bool(row["auto_enabled"]),
        state=str(row["state"]),
        round_id=int(row["round_id"]),
        round_opened_at=row["round_opened_at"],
        closes_at=row["closes_at"],
        cooldown_until=row["cooldown_until"],
        collect_sec=int(row["collect_sec"]),
        cooldown_sec=int(row["cooldown_sec"]),
        race_delay_sec=int(row["race_delay_sec"]),
        last_result=_parse_json(row["last_result"]),
        race_progress=_parse_json(row["race_progress"]),
        fixed_odds=fixed_odds,
    )


def _row_to_bet(row) -> RacesBet:
    return RacesBet(
        round_id=int(row["round_id"]),
        user_id=str(row["user_id"]),
        user_name=str(row["user_name"]),
        amount=int(row["amount"]),
        horse_number=int(row["horse_number"]),
    )


def _row_to_lineup(row) -> LineupEntry:
    return LineupEntry(
        horse_number=int(row["horse_number"]),
        princess_name=str(row["princess_name"]),
    )


def _row_to_stats(row) -> PrincessStats:
    return PrincessStats(
        princess_name=str(row["princess_name"]),
        races_count=int(row["races_count"]),
        wins_count=int(row["wins_count"]),
    )


async def get_meta(db: Database) -> RacesMeta:
    row = await db.fetchone("SELECT * FROM races_meta WHERE id = 1")
    if row is None:
        raise RuntimeError("races_meta row missing")
    return _row_to_meta(row)


async def update_meta(db: Database, **fields: Any) -> None:
    if not fields:
        return
    for key in ("last_result", "race_progress", "fixed_odds"):
        if key in fields and fields[key] is not None:
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
    if "auto_enabled" in fields:
        fields["auto_enabled"] = 1 if fields["auto_enabled"] else 0
    cols = ", ".join(f"{k} = ?" for k in fields)
    params = tuple(fields.values())
    await db.execute(f"UPDATE races_meta SET {cols} WHERE id = 1", params)


async def has_bet(db: Database, round_id: int, user_id: str) -> bool:
    row = await db.fetchone(
        "SELECT 1 FROM races_bets WHERE round_id = ? AND user_id = ?",
        (round_id, str(user_id)),
    )
    return row is not None


async def add_bet(db: Database, bet: RacesBet) -> None:
    await db.execute(
        """
        INSERT INTO races_bets (
            round_id, user_id, user_name, amount, horse_number
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            bet.round_id,
            bet.user_id,
            bet.user_name,
            bet.amount,
            bet.horse_number,
        ),
    )


async def list_bets(db: Database, round_id: int) -> list[RacesBet]:
    rows = await db.fetchall(
        """
        SELECT * FROM races_bets
        WHERE round_id = ?
        ORDER BY id
        """,
        (round_id,),
    )
    return [_row_to_bet(row) for row in rows]


async def delete_bets(db: Database, round_id: int) -> None:
    await db.execute("DELETE FROM races_bets WHERE round_id = ?", (round_id,))


async def save_lineup(db: Database, round_id: int, entries: list[LineupEntry]) -> None:
    await db.execute("DELETE FROM races_lineup WHERE round_id = ?", (round_id,))
    for entry in entries:
        await db.execute(
            """
            INSERT INTO races_lineup (round_id, horse_number, princess_name)
            VALUES (?, ?, ?)
            """,
            (round_id, entry.horse_number, entry.princess_name),
        )


async def get_lineup(db: Database, round_id: int) -> list[LineupEntry]:
    rows = await db.fetchall(
        """
        SELECT horse_number, princess_name FROM races_lineup
        WHERE round_id = ?
        ORDER BY horse_number
        """,
        (round_id,),
    )
    return [_row_to_lineup(row) for row in rows]


async def get_princess_stats(db: Database, princess_name: str) -> PrincessStats:
    row = await db.fetchone(
        "SELECT * FROM races_princess_stats WHERE princess_name = ?",
        (princess_name,),
    )
    if row is None:
        return PrincessStats(princess_name=princess_name, races_count=0, wins_count=0)
    return _row_to_stats(row)


async def list_princess_stats(db: Database) -> list[PrincessStats]:
    rows = await db.fetchall("SELECT * FROM races_princess_stats ORDER BY princess_name")
    return [_row_to_stats(row) for row in rows]


async def list_all_princess_stats(db: Database) -> list[PrincessStats]:
    """Все принцессы из справочника с историей (0 если ещё не бегали)."""
    from bot.princesses import DISNEY_PRINCESSES

    by_name = {s.princess_name: s for s in await list_princess_stats(db)}
    return [
        by_name.get(
            name,
            PrincessStats(princess_name=name, races_count=0, wins_count=0),
        )
        for name in DISNEY_PRINCESSES
    ]


async def record_race_result(
    db: Database,
    princess_names: list[str],
    winner_name: str,
) -> None:
    for name in princess_names:
        stats = await get_princess_stats(db, name)
        wins = stats.wins_count + (1 if name == winner_name else 0)
        await db.execute(
            """
            INSERT INTO races_princess_stats (princess_name, races_count, wins_count)
            VALUES (?, 1, ?)
            ON CONFLICT(princess_name) DO UPDATE SET
                races_count = races_count + 1,
                wins_count = wins_count + excluded.wins_count
            """,
            (name, 1 if name == winner_name else 0),
        )
