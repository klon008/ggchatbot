"""One-off: generate placeholder princess SVG icons."""
from __future__ import annotations

import hashlib
from pathlib import Path

from bot.princesses import DISNEY_PRINCESSES, PRINCESS_ICON_SLUG

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / "obs" / "assets" / "princesses"
out.mkdir(parents=True, exist_ok=True)

for name in DISNEY_PRINCESSES:
    slug = PRINCESS_ICON_SLUG[name]
    letter = name[0]
    h = int(hashlib.md5(slug.encode()).hexdigest()[:6], 16)
    hue = h % 360
    color = f"hsl({hue}, 65%, 55%)"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
        f'  <circle cx="32" cy="32" r="30" fill="{color}" stroke="#fff" stroke-width="3"/>\n'
        f'  <text x="32" y="40" text-anchor="middle" font-family="Arial,sans-serif" '
        f'font-size="28" font-weight="bold" fill="#fff">{letter}</text>\n'
        f"</svg>\n"
    )
    (out / f"{slug}.svg").write_text(svg, encoding="utf-8")

print(f"Generated {len(DISNEY_PRINCESSES)} SVG files in {out}")
