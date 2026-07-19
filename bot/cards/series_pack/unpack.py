from __future__ import annotations

import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class PackData:
    root: Path
    manifest: dict[str, Any]
    series: dict[str, Any]
    stories: dict[str, str]


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if not name or name.endswith("/"):
            continue
        if name.startswith("/") or Path(name).is_absolute():
            raise ValueError(f"Абсолютный путь в ZIP: {info.filename}")
        target = (dest / name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise ValueError(f"Zip-slip: {info.filename}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


def unpack_zip(zip_path: Path, tmp_root: Path) -> PackData:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = tmp_root / stamp
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        _safe_extract(zf, dest)

    manifest_path = dest / "MANIFEST.json"
    series_path = dest / "series.json"
    stories_path = dest / "stories.json"
    if not manifest_path.is_file():
        raise ValueError("В ZIP нет MANIFEST.json")
    if not series_path.is_file():
        raise ValueError("В ZIP нет series.json")
    if not stories_path.is_file():
        raise ValueError("В ZIP нет stories.json")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    series_doc = json.loads(series_path.read_text(encoding="utf-8"))
    stories_doc = json.loads(stories_path.read_text(encoding="utf-8"))
    stories = stories_doc.get("stories") if isinstance(stories_doc, dict) else None
    if not isinstance(stories, dict):
        raise ValueError("stories.json: ожидается { v, stories: { slug: text } }")

    return PackData(
        root=dest,
        manifest=manifest,
        series=series_doc,
        stories={str(k): str(v) for k, v in stories.items()},
    )


def cleanup_tmp(pack_root: Path) -> None:
    if pack_root.exists():
        shutil.rmtree(pack_root, ignore_errors=True)
