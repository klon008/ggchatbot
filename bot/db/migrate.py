"""Apply pending schema migrations."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from .migrations import MIGRATIONS

log = logging.getLogger("bot.db")


async def get_schema_version(conn: aiosqlite.Connection) -> int:
    async with conn.execute("SELECT version FROM schema_version WHERE id = 1") as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 1


def _backup_db(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = db_path.parent / f"backup-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, backup_dir / db_path.name)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if not sidecar.exists():
            continue
        try:
            shutil.copy2(sidecar, backup_dir / sidecar.name)
        except OSError:
            log.warning("Skip backup of %s (file in use)", sidecar.name)
    log.info("Backup before migration: %s", backup_dir)
    return backup_dir


async def run_migrations(
    conn: aiosqlite.Connection,
    *,
    db_path: Optional[Path] = None,
) -> int:
    """Apply pending migrations. Returns final schema version."""
    current = await get_schema_version(conn)
    pending = [m for m in MIGRATIONS if m.VERSION > current]

    if not pending:
        log.info("Schema version %d (up to date)", current)
        return current

    if db_path is not None and db_path.exists():
        _backup_db(db_path)

    for migration in pending:
        log.info(
            "Applying migration %d: %s",
            migration.VERSION,
            migration.DESCRIPTION,
        )
        await migration.upgrade(conn)
        await conn.execute(
            "UPDATE schema_version SET version = ? WHERE id = 1",
            (migration.VERSION,),
        )
        await conn.commit()
        current = migration.VERSION

    log.info("Schema version %d (up to date)", current)
    return current
