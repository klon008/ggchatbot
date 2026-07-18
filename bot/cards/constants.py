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

# Доля от стоимости 1 карты в наборе при возврате за дубликат.
DUPLICATE_REFUND_RATES: dict[str, float] = {
    "common": 0.25,
    "uncommon": 0.50,
    "rare": 0.70,
    "epic": 1.00,
    "legendary": 1.50,
    "mythic": 2.00,
    "secretRare": 5.00,
}
