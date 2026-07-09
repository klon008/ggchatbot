"""One-time migration from JSON stores to data/bot.db.

Usage (PowerShell):
    python scripts/migrate_json_to_sqlite.py
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.db import Database, DATA_DIR  # noqa: E402

POINTS_FILE = DATA_DIR / "princess_points.json"
STEAL_FILE = DATA_DIR / "steal_chance_and_count.json"
DAILY_FILE = DATA_DIR / "daily_bonus.json"
QUEUE_FILE = DATA_DIR / "queue.json"
DB_FILE = DATA_DIR / "bot.db"

_DATE_KEY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _backup_data_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATA_DIR / f"backup-{stamp}"
    if DATA_DIR.exists():
        shutil.copytree(DATA_DIR, backup, ignore=shutil.ignore_patterns("backup-*", "*.db", "*.db-*"))
    else:
        backup.mkdir(parents=True)
    print(f"Backup: {backup}")
    return backup


async def _import_points(conn, data: dict) -> int:
    total = 0
    for user_id, balance in data.items():
        await conn.execute(
            "INSERT INTO points (user_id, balance) VALUES (?, ?)",
            (str(user_id), int(balance)),
        )
        total += int(balance)
    return total


async def _import_steal(conn, data: dict) -> int:
    count = 0
    for user_id, info in data.items():
        await conn.execute(
            "INSERT INTO steal_stats "
            "(user_id, attempts, success, stolen_total, chance, last_time, times_in_jail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(user_id),
                int(info.get("attempts", 0)),
                int(info.get("success", 0)),
                int(info.get("stolen_total", 0)),
                int(info.get("chance", 3)),
                float(info.get("last_time", 0)),
                int(info.get("times_in_jail", 0)),
            ),
        )
        count += 1
    return count


async def _import_daily(conn, data: dict) -> None:
    current_month = str(data.get("current_month", ""))
    await conn.execute(
        "UPDATE daily_meta SET current_month = ? WHERE id = 1",
        (current_month,),
    )
    progress = data.get("user_progress", {})
    if current_month and isinstance(progress, dict):
        for user_id, counter in progress.items():
            await conn.execute(
                "INSERT INTO daily_progress (user_id, month, counter) VALUES (?, ?, ?)",
                (str(user_id), current_month, int(counter)),
            )
    for key, value in data.items():
        if not _DATE_KEY.match(key) or not isinstance(value, list):
            continue
        for user_id in value:
            await conn.execute(
                "INSERT OR IGNORE INTO daily_claims (user_id, day) VALUES (?, ?)",
                (str(user_id), key),
            )


async def _import_queue(conn, data: dict) -> int:
    current = data.get("current")
    queue = list(data.get("queue", []))
    token_counter = 1
    if current:
        current_token = "t-1"
        token_counter = 2
        current_json = json.dumps(current, ensure_ascii=False)
    else:
        current_token = None
        current_json = None

    await conn.execute(
        "UPDATE queue_meta SET current_json = ?, current_token = ?, token_counter = ? WHERE id = 1",
        (current_json, current_token, token_counter),
    )

    position = 0
    for item in queue:
        await conn.execute(
            "INSERT INTO queue_items "
            "(position, video_id, requested_by, requested_by_name, url, title, added_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                position,
                item["video_id"],
                item["requested_by"],
                item.get("requested_by_name", ""),
                item["url"],
                item.get("title", ""),
                float(item.get("added_at", 0)),
            ),
        )
        position += 1
    return position + (1 if current else 0)


async def migrate() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _backup_data_dir()

    points_data = _read_json(POINTS_FILE, {})
    steal_data = _read_json(STEAL_FILE, {})
    daily_data = _read_json(DAILY_FILE, {"current_month": "", "user_progress": {}})
    queue_data = _read_json(QUEUE_FILE, {"current": None, "queue": []})

    if DB_FILE.exists():
        print(f"Removing existing {DB_FILE} for fresh migration.")
        DB_FILE.unlink()

    db = Database(DB_FILE)
    await db.open()
    conn = db.conn

    json_points_sum = await _import_points(conn, points_data)
    steal_count = await _import_steal(conn, steal_data)
    await _import_daily(conn, daily_data)
    queue_len = await _import_queue(conn, queue_data)
    await conn.commit()

    row = await db.fetchone("SELECT COALESCE(SUM(balance), 0) AS total FROM points")
    db_points_sum = int(row["total"]) if row else 0
    row = await db.fetchone("SELECT COUNT(*) AS n FROM steal_stats")
    db_steal_count = int(row["n"]) if row else 0
    row = await db.fetchone("SELECT COUNT(*) AS n FROM queue_items")
    db_queue_items = int(row["n"]) if row else 0
    meta = await db.fetchone("SELECT current_json FROM queue_meta WHERE id = 1")
    db_queue_len = db_queue_items + (1 if meta and meta["current_json"] else 0)

    json_queue_len = len(queue_data.get("queue", [])) + (1 if queue_data.get("current") else 0)

    ok = True
    if json_points_sum != db_points_sum:
        print(f"[FAIL] points sum: JSON={json_points_sum} DB={db_points_sum}")
        ok = False
    else:
        print(f"[OK] points sum: {db_points_sum}")

    if steal_count != db_steal_count:
        print(f"[FAIL] steal rows: JSON={steal_count} DB={db_steal_count}")
        ok = False
    else:
        print(f"[OK] steal rows: {db_steal_count}")

    if json_queue_len != db_queue_len:
        print(f"[FAIL] queue length: JSON={json_queue_len} DB={db_queue_len}")
        ok = False
    else:
        print(f"[OK] queue length: {db_queue_len}")

    if not ok:
        await db.close()
        print("Migration verification failed — JSON files not renamed.")
        return 1

    for path in (POINTS_FILE, STEAL_FILE, DAILY_FILE, QUEUE_FILE):
        if path.exists():
            bak = path.with_suffix(path.suffix + ".bak")
            path.rename(bak)
            print(f"Renamed: {path.name} -> {bak.name}")

    await db.close()
    print("Migration completed successfully.")
    return 0


def main() -> int:
    return asyncio.run(migrate())


if __name__ == "__main__":
    sys.exit(main())
