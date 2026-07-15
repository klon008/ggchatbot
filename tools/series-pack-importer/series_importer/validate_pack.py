from __future__ import annotations

import re
from pathlib import Path

from .unpack import PackData

RARITIES = {
    "common",
    "uncommon",
    "rare",
    "epic",
    "legendary",
    "mythic",
    "secretRare",
}
SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
BACK_RE = re.compile(r"^card-back-[a-z0-9_-]+$")


def validate_roots(bot_root: Path, fe_root: Path) -> list[str]:
    errs: list[str] = []
    if not (bot_root / "main.py").is_file() and not (bot_root / "bot").is_dir():
        errs.append(f"Bot root не похож на botmsc: {bot_root}")
    if not (bot_root / "bot" / "db" / "migrations").is_dir():
        errs.append(f"Нет bot/db/migrations в {bot_root}")
    if not (fe_root / "package.json").is_file():
        errs.append(f"Frontend root без package.json: {fe_root}")
    if not (fe_root / "src" / "imports").is_dir():
        errs.append(f"Нет src/imports в {fe_root}")
    return errs


def validate_pack(pack: PackData, bot_root: Path, fe_root: Path) -> list[str]:
    errs: list[str] = []
    mf = pack.manifest
    doc = pack.series

    pv = mf.get("pack_version", doc.get("pack_version"))
    if pv != 1:
        errs.append(f"pack_version={pv}, ожидается 1")

    series = doc.get("series") or {}
    booster = doc.get("booster") or {}
    draw = doc.get("draw") or {}
    cards = doc.get("cards") or []

    sid = str(series.get("id", "")).strip().lower()
    sname = str(series.get("name", "")).strip()
    back_id = str(series.get("card_back_id", "")).strip().lower()
    if not SLUG_RE.match(sid):
        errs.append("series.id: невалидный slug")
    if not sname:
        errs.append("series.name: пусто")
    if not BACK_RE.match(back_id):
        errs.append("series.card_back_id: нужен card-back-*")

    bid = str(booster.get("id", "")).strip().lower()
    if not SLUG_RE.match(bid):
        errs.append("booster.id: невалидный slug")
    if not str(booster.get("name", "")).strip():
        errs.append("booster.name: пусто")

    did = str(draw.get("id", "")).strip().lower()
    if not SLUG_RE.match(did):
        errs.append("draw.id: невалидный slug")
    if int(draw.get("cost_points") or 0) <= 0:
        errs.append("draw.cost_points: > 0")
    if int(draw.get("cards_per_open") or 0) < 1:
        errs.append("draw.cards_per_open: >= 1")

    if not isinstance(cards, list) or not cards:
        errs.append("cards: пустой список")
        return errs

    seen: set[str] = set()
    for i, c in enumerate(cards, 1):
        cid = str(c.get("id", "")).strip().lower()
        if not SLUG_RE.match(cid):
            errs.append(f"card#{i} id: невалидный slug")
            continue
        if cid in seen:
            errs.append(f"Дубль card id: {cid}")
        seen.add(cid)
        if not str(c.get("name", "")).strip():
            errs.append(f"{cid}: name пусто")
        rar = str(c.get("rarity", ""))
        if rar not in RARITIES:
            errs.append(f"{cid}: rarity={rar}")
        story = pack.stories.get(cid, "").strip()
        if not story:
            errs.append(f"{cid}: нет story в stories.json")
        rel = str(c.get("file") or f"cards/{cid}.webp")
        fpath = pack.root / rel
        if not fpath.is_file():
            errs.append(f"{cid}: нет файла {rel}")

    back_file = series.get("card_back_file") or f"backs/{back_id}.svg"
    if not (pack.root / back_file).is_file():
        errs.append(f"Нет рубашки {back_file}")

    # Conflicts with existing frontend / bot assets / catalog
    fe_imports = fe_root / "src" / "imports"
    bot_assets = bot_root / "obs" / "assets" / "cards"
    catalog = (fe_root / "src" / "lib" / "cardCatalog.ts").read_text(encoding="utf-8")
    mig_dir = bot_root / "bot" / "db" / "migrations"
    mig_text = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in mig_dir.glob("m*.py")
    )

    if re.search(rf'["\']id["\']:\s*["\']{re.escape(sid)}["\']|_SERIES_ID\s*=\s*["\']{re.escape(sid)}["\']', mig_text):
        errs.append(f"series.id «{sid}» уже встречается в миграциях")
    if f'"{sid}"' in catalog or f"'{sid}'" in catalog:
        # series id rarely in catalog; check card ids instead
        pass
    if re.search(rf'_BOOSTER_ID\s*=\s*["\']{re.escape(bid)}["\']', mig_text):
        errs.append(f"booster.id «{bid}» уже есть в миграциях")
    if re.search(rf'_DRAW_ID\s*=\s*["\']{re.escape(did)}["\']', mig_text):
        errs.append(f"draw.id «{did}» уже есть в миграциях")

    for cid in seen:
        if re.search(rf'["\']{re.escape(cid)}["\']', catalog):
            errs.append(f"card id «{cid}» уже в cardCatalog.ts")
        if (fe_imports / f"{cid}.webp").exists():
            errs.append(f"Уже есть frontend import: {cid}.webp")
        if (bot_assets / f"{cid}.webp").exists():
            errs.append(f"Уже есть bot asset: {cid}.webp")

    if (fe_imports / f"{back_id}.svg").exists():
        errs.append(f"Уже есть frontend рубашка: {back_id}.svg")
    if (bot_assets / f"{back_id}.svg").exists():
        errs.append(f"Уже есть bot рубашка: {back_id}.svg")

    return errs
