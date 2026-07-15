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


def unpack_zip(zip_path: Path, tmp_root: Path) -> PackData:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = tmp_root / stamp
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)

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
    parent = pack_root.parent
    if parent.name == "tmp" and pack_root.exists():
        shutil.rmtree(pack_root, ignore_errors=True)
