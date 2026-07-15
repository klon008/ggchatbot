from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

RARITIES: tuple[str, ...] = (
    "common",
    "uncommon",
    "rare",
    "epic",
    "legendary",
    "mythic",
    "secretRare",
)

# Colors from princtascdwk src/app/rarityConfig.ts
RARITY_COLORS: dict[str, str] = {
    "common": "#9A8050",
    "uncommon": "#7AD868",
    "rare": "#5898FF",
    "epic": "#9070F0",
    "legendary": "#FFB020",
    "mythic": "#660f00",
    "secretRare": "#D4567A",
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "common": 48.0,
    "uncommon": 24.0,
    "rare": 12.0,
    "epic": 7.0,
    "legendary": 5.0,
    "mythic": 1.0,
    "secretRare": 1.0,
}

SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
CARD_BACK_ID_RE = re.compile(r"^card-back-[a-z0-9_-]+$")
NAME_MAX = 64
STORY_MAX = 2000
TARGET_W = 310
TARGET_H = 330
PACK_VERSION = 1
TELEGRAM_URL = "https://t.me/klon_008"


@dataclass
class SeriesDraft:
    series_id: str = ""
    name: str = ""
    card_back_id: str = ""
    card_back_path: Optional[Path] = None
    sort_order: int = 1


@dataclass
class CardDraft:
    source_path: Optional[Path] = None
    # In-memory original bytes / PIL will use source_path or paste_image
    paste_image: object = None  # PIL.Image.Image | None
    card_id: str = ""
    name: str = ""
    rarity: str = "common"
    story: str = ""


@dataclass
class BoosterDraft:
    booster_id: str = ""
    name: str = ""
    promo_image_url: str = ""


@dataclass
class DrawDraft:
    draw_id: str = ""
    name: str = "Тираж № 001"
    cost_points: int = 15000
    cards_per_open: int = 6
    daily_limit: int = 0
    rarity_weights: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_WEIGHTS)
    )
    status: str = "queued"


@dataclass
class PackDraft:
    series: SeriesDraft = field(default_factory=SeriesDraft)
    cards: list[CardDraft] = field(default_factory=list)
    booster: BoosterDraft = field(default_factory=BoosterDraft)
    draw: DrawDraft = field(default_factory=DrawDraft)
