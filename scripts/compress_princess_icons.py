"""Compress obs/assets/zabeg/*.png into obs/assets/princesses/{slug}.webp."""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "obs" / "assets" / "zabeg"
OUT = ROOT / "obs" / "assets" / "princesses"
SIZE = 128
QUALITY = 82

# Keep in sync with bot/princesses.py PRINCESS_ICON_SLUG
PRINCESS_ICON_SLUG: dict[str, str] = {
    "Белоснежка": "belosnezhka",
    "Аврора": "avrora",
    "Золушка": "zolushka",
    "Мулан": "mulan",
    "Рапунцель": "rapuntsel",
    "Тиана": "tiana",
    "Покахонтас": "pokahontas",
    "Ариэль": "ariel",
    "Жасмин": "zhasmin",
    "Эльза": "elza",
    "Анна": "anna",
    "Моана": "moana",
    "Мерида": "merida",
    "Бэлль": "bell",
    "Ванилопа": "vanilopa",
    "Алиса": "alisa",
    "Эсмеральда": "esmeralda",
    "Кида": "kida",
    "Мегара": "megara",
    "Райя": "raya",
    "Джейн Портер": "jane_porter",
}

# Filename stem (without " 1") → canonical princess name
FILE_ALIASES: dict[str, str] = {
    "Белль": "Бэлль",
    "Джейн": "Джейн Портер",
}


def to_circular(img: Image.Image) -> Image.Image:
    """Square RGBA with opaque disk and transparent corners."""
    size = img.size[0]
    out = img.convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    # Soft edge to avoid jagged halo at 40px display size
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    r, g, b, a = out.split()
    # Combine existing alpha with circular mask
    a = Image.composite(a, Image.new("L", (size, size), 0), mask)
    out.putalpha(a)
    return out


def stem_to_name(stem: str) -> str | None:
    base = re.sub(r"\s+\d+$", "", stem).strip()
    if base in PRINCESS_ICON_SLUG:
        return base
    return FILE_ALIASES.get(base)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    total_in = 0
    total_out = 0

    for src in sorted(SRC.glob("*.png")):
        name = stem_to_name(src.stem)
        if name is None:
            print(f"SKIP unknown: {src.name!r}")
            continue
        slug = PRINCESS_ICON_SLUG[name]
        dest = OUT / f"{slug}.webp"

        img = Image.open(src).convert("RGBA")
        img = img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        img = to_circular(img)
        img.save(dest, "WEBP", quality=QUALITY, method=6)

        total_in += src.stat().st_size
        total_out += dest.stat().st_size
        seen.add(name)
        print(f"{src.name} → {dest.name}  {src.stat().st_size // 1024}KB → {dest.stat().st_size // 1024}KB")

    missing = sorted(set(PRINCESS_ICON_SLUG) - seen)
    if missing:
        print("MISSING:", ", ".join(missing))
        raise SystemExit(1)

    # Drop placeholder SVGs once webp exists
    for svg in OUT.glob("*.svg"):
        if (OUT / f"{svg.stem}.webp").exists():
            svg.unlink()
            print(f"removed placeholder {svg.name}")

    print(
        f"Done: {len(seen)} icons, "
        f"{total_in // 1024}KB → {total_out // 1024}KB "
        f"({100 * total_out / max(1, total_in):.1f}%)"
    )


if __name__ == "__main__":
    main()
