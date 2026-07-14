"""Константы модуля коллекционных карт."""

from __future__ import annotations

ALBUM_API_HOST = "127.0.0.1"
ALBUM_API_PORT = 18770

ALBUM_TOKEN_TTL_SEC = 24 * 60 * 60
ALBUM_API_RATE_LIMIT_PER_MIN = 60

RARITY_LABELS: dict[str, str] = {
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "epic": "Epic",
    "legendary": "Legendary",
    "mythic": "Mythic",
    "secretRare": "Secret Rare",
}
