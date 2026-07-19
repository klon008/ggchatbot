"""High-level build / import for web admin."""

from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional

from .apply_bot import apply_bot_files
from .apply_db import apply_pack_to_db
from .apply_frontend import apply_frontend
from .export import build_zip
from .gen_migration import next_migration_version
from .models import (
    DEFAULT_CARD_BACK_ID,
    DEFAULT_CARD_BACK_PATH,
    DEFAULT_WEIGHTS,
    PROJECT_ROOT,
    BoosterDraft,
    CardDraft,
    DrawDraft,
    PackDraft,
    SeriesDraft,
)
from .stories_cache import merge_stories_cache
from .unpack import cleanup_tmp, unpack_zip
from .validate import validate_draft
from .validate_pack import (
    validate_bot_root,
    validate_frontend_root,
    validate_pack,
)

if TYPE_CHECKING:
    from bot.db import Database

LogFn = Callable[[str], None]

_import_lock = asyncio.Lock()


class ImportBusyError(RuntimeError):
    pass


def resolve_draft_defaults(draft: PackDraft) -> list[str]:
    """Fill default card-back id/path when omitted. Returns errors if default missing."""
    errs: list[str] = []
    series = draft.series
    back_id = (series.card_back_id or "").strip().lower()
    if not back_id:
        series.card_back_id = DEFAULT_CARD_BACK_ID
        back_id = DEFAULT_CARD_BACK_ID
    if series.card_back_path is None or not series.card_back_path.is_file():
        if not DEFAULT_CARD_BACK_PATH.is_file():
            errs.append(
                f"Нет дефолтной рубашки: {DEFAULT_CARD_BACK_PATH.as_posix()}"
            )
        else:
            series.card_back_path = DEFAULT_CARD_BACK_PATH
            series.card_back_id = back_id or DEFAULT_CARD_BACK_ID
    return errs


def build_pack_zip(draft: PackDraft, out_dir: Path | None = None) -> tuple[Path | None, list[str]]:
    """Validate and build ZIP. Returns (path, errors)."""
    errs = resolve_draft_defaults(draft)
    errs.extend(validate_draft(draft))
    if errs:
        return None, errs
    target = out_dir or Path(tempfile.mkdtemp(prefix="series-pack-out-"))
    path = build_zip(draft, target)
    return path, []


def draft_from_meta(
    meta: dict[str, Any],
    *,
    back_path: Path | None,
    card_paths: dict[str, Path],
) -> PackDraft:
    series_raw = meta.get("series") or {}
    booster_raw = meta.get("booster") or {}
    draw_raw = meta.get("draw") or {}
    cards_raw = meta.get("cards") or []

    series = SeriesDraft(
        series_id=str(series_raw.get("series_id") or series_raw.get("id") or ""),
        name=str(series_raw.get("name") or ""),
        card_back_id=str(series_raw.get("card_back_id") or "").strip().lower(),
        card_back_path=back_path,
        sort_order=int(series_raw.get("sort_order") or 1),
    )
    booster = BoosterDraft(
        booster_id=str(booster_raw.get("booster_id") or booster_raw.get("id") or ""),
        name=str(booster_raw.get("name") or ""),
        promo_image_url=str(booster_raw.get("promo_image_url") or ""),
    )
    weights_raw = draw_raw.get("rarity_weights") or {}
    weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
    if isinstance(weights_raw, dict):
        for k, v in weights_raw.items():
            try:
                weights[str(k)] = float(v)
            except (TypeError, ValueError):
                pass
    draw = DrawDraft(
        draw_id=str(draw_raw.get("draw_id") or draw_raw.get("id") or ""),
        name=str(draw_raw.get("name") or "Тираж № 001"),
        cost_points=int(draw_raw.get("cost_points") or 15000),
        cards_per_open=int(draw_raw.get("cards_per_open") or 6),
        daily_limit=int(draw_raw.get("daily_limit") or 0),
        rarity_weights=weights,
        status=str(draw_raw.get("status") or "queued"),
    )

    cards: list[CardDraft] = []
    for c in cards_raw:
        cid = str(c.get("card_id") or c.get("id") or "").strip().lower()
        cards.append(
            CardDraft(
                source_path=card_paths.get(cid),
                card_id=cid,
                name=str(c.get("name") or ""),
                rarity=str(c.get("rarity") or "common"),
                story=str(c.get("story") or ""),
            )
        )
    return PackDraft(series=series, cards=cards, booster=booster, draw=draw)


async def import_pack_zip(
    zip_path: Path,
    db: "Database",
    *,
    bot_root: Path | None = None,
    apply_frontend_flag: bool = False,
    frontend_root: Path | None = None,
    dry_run: bool = False,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Import series-pack ZIP into bot (and optionally frontend)."""
    if _import_lock.locked():
        raise ImportBusyError("Импорт уже выполняется")

    await _import_lock.acquire()
    try:
        return await _import_pack_zip_locked(
            zip_path,
            db,
            bot_root=bot_root,
            apply_frontend_flag=apply_frontend_flag,
            frontend_root=frontend_root,
            dry_run=dry_run,
            log=log,
        )
    finally:
        _import_lock.release()


async def _import_pack_zip_locked(
    zip_path: Path,
    db: "Database",
    *,
    bot_root: Path | None,
    apply_frontend_flag: bool,
    frontend_root: Path | None,
    dry_run: bool,
    log: LogFn | None,
) -> dict[str, Any]:
    lines: list[str] = []

    def _log(msg: str) -> None:
        lines.append(msg)
        if log:
            log(msg)

    root = bot_root or PROJECT_ROOT
    warnings: list[str] = []

    root_errs = validate_bot_root(root)
    if root_errs:
        return {"ok": False, "errors": root_errs, "log": lines}

    fe: Optional[Path] = None
    if apply_frontend_flag:
        fe = frontend_root
        if fe is None:
            return {
                "ok": False,
                "errors": ["apply_frontend=1, но frontend_root не задан"],
                "log": lines,
            }
        fe_errs = validate_frontend_root(fe)
        if fe_errs:
            return {"ok": False, "errors": fe_errs, "log": lines}
    else:
        warnings.append(
            "Frontend не применялся; для альбома на GH Pages "
            "включите apply_frontend на машине с princtascdwk"
        )

    tmp_root = root / "data" / "series-pack-tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    pack = None
    try:
        _log("Распаковка ZIP…")
        pack = unpack_zip(zip_path, tmp_root)
        errs = validate_pack(pack, root, fe)
        if errs:
            return {"ok": False, "errors": errs, "log": lines, "warnings": warnings}

        doc = pack.series
        series = doc["series"]
        booster = doc["booster"]
        draw = doc["draw"]
        cards = doc["cards"]
        sid = series["id"]
        bid = booster["id"]
        did = draw["id"]

        _log(f"Preflight OK: series={sid}, cards={len(cards)}")

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "series_id": sid,
                "booster_id": bid,
                "draw_id": did,
                "cards_count": len(cards),
                "pack_version": pack.manifest.get("pack_version", doc.get("pack_version")),
                "wrote": None,
                "warnings": warnings,
                "log": lines,
            }

        if fe is not None:
            _log("Применение frontend…")
            apply_frontend(pack, fe, _log)

        _log("Копирование assets + миграция…")
        # Peek next version before write (apply_bot_files computes again)
        mig_dir = root / "bot" / "db" / "migrations"
        version = next_migration_version(mig_dir)
        mig_path = apply_bot_files(pack, root, _log)
        # version may have been taken inside apply; parse from filename
        m = re.match(r"m(\d+)_", mig_path.name)
        if m:
            version = int(m.group(1))

        _log("Запись в DB (in-process)…")
        async with db.transaction() as conn:
            await apply_pack_to_db(
                conn,
                series,
                booster,
                draw,
                cards,
                schema_version=version,
            )
        _log(f"DB OK, schema_version={version}")

        merge_stories_cache(pack.stories, _log)

        warnings.append("Активируйте тираж в cards-admin (queued → active)")

        return {
            "ok": True,
            "dry_run": False,
            "series_id": sid,
            "booster_id": bid,
            "draw_id": did,
            "cards_count": len(cards),
            "pack_version": pack.manifest.get("pack_version", doc.get("pack_version")),
            "wrote": {
                "bot_assets": f"obs/assets/cards/ ({len(cards)} webp + back)",
                "migration": str(mig_path.relative_to(root)).replace("\\", "/"),
                "db_applied": True,
                "frontend": str(fe) if fe else None,
            },
            "warnings": warnings,
            "log": lines,
        }
    finally:
        if pack is not None:
            cleanup_tmp(pack.root)
