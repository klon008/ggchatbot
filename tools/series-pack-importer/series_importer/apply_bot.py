from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .gen_migration import (
    generate_migration_source,
    next_migration_version,
    register_migration,
)
from .unpack import PackData

LogFn = Callable[[str], None]


def apply_bot(pack: PackData, bot_root: Path, run_migrate: bool, log: LogFn) -> Path:
    doc = pack.series
    series = doc["series"]
    booster = doc["booster"]
    draw = doc["draw"]
    cards: list[dict] = doc["cards"]
    sid = series["id"]
    back_id = series["card_back_id"]

    assets = bot_root / "obs" / "assets" / "cards"
    assets.mkdir(parents=True, exist_ok=True)

    back_rel = series.get("card_back_file") or f"backs/{back_id}.svg"
    shutil.copy2(pack.root / back_rel, assets / f"{back_id}.svg")
    log(f"Bot рубашка → obs/assets/cards/{back_id}.svg")

    for c in cards:
        cid = c["id"]
        rel = c.get("file") or f"cards/{cid}.webp"
        shutil.copy2(pack.root / rel, assets / f"{cid}.webp")
    log(f"Bot webp: {len(cards)} файлов")

    mig_dir = bot_root / "bot" / "db" / "migrations"
    version = next_migration_version(mig_dir)
    module = f"m{version:03d}_series_{sid.replace('-', '_')}"
    file_name = f"{module}.py"
    source = generate_migration_source(version, series, booster, draw, cards)
    mig_path = mig_dir / file_name
    mig_path.write_text(source, encoding="utf-8", newline="\n")
    log(f"Миграция → {mig_path.name} (VERSION={version})")

    register_migration(mig_dir / "__init__.py", module)
    log("migrations/__init__.py обновлён")

    if run_migrate:
        _run_migrate(bot_root, log)
    else:
        log("migrate_db.py пропущен (checkbox выключен)")

    return mig_path


def _run_migrate(bot_root: Path, log: LogFn) -> None:
    venv_py = bot_root / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.is_file() else "python"
    script = bot_root / "scripts" / "migrate_db.py"
    log(f"Запуск: {py} scripts/migrate_db.py …")
    proc = subprocess.run(
        [py, str(script)],
        cwd=str(bot_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout:
        log(proc.stdout.strip())
    if proc.stderr:
        log(proc.stderr.strip())
    if proc.returncode != 0:
        raise RuntimeError(
            f"migrate_db.py завершился с кодом {proc.returncode}. "
            "Остановите бота и повторите."
        )
    log("migrate_db.py OK")
