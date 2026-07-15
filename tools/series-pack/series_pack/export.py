from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .image_proc import cover_crop_to_size, load_image, save_card_webp
from .models import PACK_VERSION, PackDraft


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_zip(draft: PackDraft, out_dir: Path | None = None) -> Path:
    """Build ZIP from draft. Writes no DB. Returns path to archive."""
    series = draft.series
    booster = draft.booster
    draw = draft.draw

    series_id = series.series_id.strip().lower()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_name = f"series-{series_id}-{stamp}.zip"
    target_dir = out_dir or Path.home() / "Downloads"
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / zip_name

    tmp = Path(tempfile.mkdtemp(prefix="series-pack-"))
    try:
        backs = tmp / "backs"
        cards_dir = tmp / "cards"
        backs.mkdir()
        cards_dir.mkdir()

        back_id = series.card_back_id.strip().lower()
        assert series.card_back_path is not None
        shutil.copy2(series.card_back_path, backs / f"{back_id}.svg")

        cards_meta: list[dict] = []
        stories: dict[str, str] = {}

        for idx, card in enumerate(draft.cards):
            cid = card.card_id.strip().lower()
            img = load_image(card.source_path, card.paste_image)  # type: ignore[arg-type]
            webp = cover_crop_to_size(img)
            rel = f"cards/{cid}.webp"
            save_card_webp(webp, tmp / rel)
            cards_meta.append(
                {
                    "id": cid,
                    "name": card.name.strip(),
                    "rarity": card.rarity,
                    "sort_order": idx,
                    "file": rel,
                }
            )
            stories[cid] = card.story.strip()

        series_json = {
            "pack_version": PACK_VERSION,
            "series": {
                "id": series_id,
                "name": series.name.strip(),
                "card_back_id": back_id,
                "card_back_file": f"backs/{back_id}.svg",
                "sort_order": int(series.sort_order),
            },
            "booster": {
                "id": booster.booster_id.strip().lower(),
                "name": booster.name.strip(),
                "promo_image_url": (booster.promo_image_url or "").strip() or None,
            },
            "draw": {
                "id": draw.draw_id.strip().lower(),
                "name": draw.name.strip(),
                "cost_points": int(draw.cost_points),
                "cards_per_open": int(draw.cards_per_open),
                "daily_limit": int(draw.daily_limit),
                "rarity_weights": {
                    k: float(draw.rarity_weights.get(k, 0) or 0)
                    for k in (
                        "common",
                        "uncommon",
                        "rare",
                        "epic",
                        "legendary",
                        "mythic",
                        "secretRare",
                    )
                },
                "status": draw.status or "queued",
            },
            "cards": cards_meta,
        }

        manifest = {
            "pack_version": PACK_VERSION,
            "tool": "series-pack",
            "tool_version": __version__,
            "created_at": _utcnow(),
            "series_id": series_id,
            "cards_count": len(cards_meta),
        }

        (tmp / "series.json").write_text(
            json.dumps(series_json, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (tmp / "stories.json").write_text(
            json.dumps({"v": 1, "stories": stories}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )
        (tmp / "MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in tmp.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(tmp).as_posix())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return zip_path
