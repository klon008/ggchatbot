"""Apply pending SQLite schema migrations (without starting the bot).

Usage (PowerShell):
    python scripts/migrate_db.py

Stop the bot before running — otherwise database is locked on Windows.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.db import Database  # noqa: E402
from bot.db.migrate import get_schema_version  # noqa: E402


async def main() -> int:
    db = Database()
    try:
        await db.open()
        current = await get_schema_version(db.conn)
        print(f"[OK] Schema version {current}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[ОШИБКА] {exc}", file=sys.stderr)
        print("Остановите бота (start.cmd) и повторите.", file=sys.stderr)
        return 1
    finally:
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
