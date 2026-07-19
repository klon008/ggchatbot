from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from PIL import Image

from .models import TARGET_H, TARGET_W


def slug_guess_from_filename(path: Path | str) -> str:
    stem = Path(path).stem.strip().lower()
    stem = re.sub(r"[^a-z0-9_-]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-_")
    if not stem:
        return ""
    if stem[0].isdigit():
        stem = f"c-{stem}"
    return stem


def load_image(
    card_source: Path | None,
    paste_image: Image.Image | None = None,
    *,
    raw_bytes: bytes | None = None,
) -> Image.Image:
    if paste_image is not None:
        img = paste_image.convert("RGBA") if paste_image.mode != "RGBA" else paste_image.copy()
        return img
    if raw_bytes is not None:
        return Image.open(BytesIO(raw_bytes)).convert("RGBA")
    if card_source is None:
        raise ValueError("нет изображения")
    return Image.open(card_source).convert("RGBA")


def cover_crop_to_size(img: Image.Image, tw: int = TARGET_W, th: int = TARGET_H) -> Image.Image:
    """Center-crop cover to exact tw×th, flatten transparency on dark bg → RGB."""
    src = img.convert("RGBA")
    sw, sh = src.size
    if sw < 1 or sh < 1:
        raise ValueError("пустое изображение")

    scale = max(tw / sw, th / sh)
    nw, nh = max(1, int(round(sw * scale))), max(1, int(round(sh * scale)))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    cropped = resized.crop((left, top, left + tw, top + th))

    bg = Image.new("RGB", (tw, th), (8, 10, 20))
    bg.paste(cropped, mask=cropped.split()[-1] if cropped.mode == "RGBA" else None)
    return bg


def save_card_webp(img_rgb: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img_rgb.save(dest, "WEBP", quality=90, method=6)
