# -*- coding: utf-8 -*-
"""Smoke: build a mini pack ZIP and import into temp copies of catalog files logic."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from series_importer.gen_migration import generate_migration_source, next_migration_version
from series_importer.unpack import unpack_zip
from series_importer.validate_pack import validate_pack

BOT = Path(r"E:\programs\OBS\botmsc")
FE = Path(r"E:\Work\dartvalkkiprincess\princtascdwk")
TOOL = Path(__file__).resolve().parent


def make_fixture_zip(dest: Path) -> Path:
    root = Path(tempfile.mkdtemp(prefix="pack-fix-"))
    (root / "backs").mkdir()
    (root / "cards").mkdir()
    (root / "backs" / "card-back-smoke.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 350 490"/>',
        encoding="utf-8",
    )
    # minimal valid webp via Pillow if available, else skip — write raw empty webp header?
    try:
        from PIL import Image

        Image.new("RGB", (310, 330), (40, 60, 90)).save(
            root / "cards" / "smoke-hero.webp", "WEBP"
        )
    except ImportError:
        raise SystemExit("Pillow required for smoke (use series-pack venv or pip install pillow)")

    series = {
        "pack_version": 1,
        "series": {
            "id": "smoke",
            "name": "Smoke Set",
            "card_back_id": "card-back-smoke",
            "card_back_file": "backs/card-back-smoke.svg",
            "sort_order": 9,
        },
        "booster": {"id": "smoke", "name": "Smoke Booster", "promo_image_url": None},
        "draw": {
            "id": "draw-smoke-001",
            "name": "Тираж № 001",
            "cost_points": 1000,
            "cards_per_open": 3,
            "daily_limit": 0,
            "rarity_weights": {
                "common": 0,
                "uncommon": 0,
                "rare": 10,
                "epic": 0,
                "legendary": 0,
                "mythic": 0,
                "secretRare": 0,
            },
            "status": "queued",
        },
        "cards": [
            {
                "id": "smoke-hero",
                "name": "Смоук",
                "rarity": "rare",
                "sort_order": 0,
                "file": "cards/smoke-hero.webp",
            }
        ],
    }
    stories = {"v": 1, "stories": {"smoke-hero": "Тестовое описание смоук-героя."}}
    manifest = {
        "pack_version": 1,
        "tool": "series-pack",
        "tool_version": "1.0.0",
        "series_id": "smoke",
        "cards_count": 1,
    }
    (root / "series.json").write_text(
        json.dumps(series, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "stories.json").write_text(
        json.dumps(stories, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    zpath = dest / "series-smoke-fixture.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        for p in root.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(root).as_posix())
    shutil.rmtree(root, ignore_errors=True)
    return zpath


def main() -> None:
    tmp = TOOL / "tmp"
    tmp.mkdir(exist_ok=True)
    zpath = make_fixture_zip(tmp)
    pack = unpack_zip(zpath, tmp)
    errs = validate_pack(pack, BOT, FE)
    print("validate_pack:", errs)
    assert not errs, errs

    ver = next_migration_version(BOT / "bot" / "db" / "migrations")
    src = generate_migration_source(
        ver,
        pack.series["series"],
        pack.series["booster"],
        pack.series["draw"],
        pack.series["cards"],
    )
    assert f"VERSION = {ver}" in src
    assert "_SERIES_ID = \"smoke\"" in src or "_SERIES_ID = 'smoke'" in src or '"smoke"' in src
    assert "smoke-hero" in src
    print("migration preview OK, next VERSION would be", ver)
    print("zip", zpath)
    print("SMOKE OK (no filesystem mutate of repos)")


if __name__ == "__main__":
    main()
