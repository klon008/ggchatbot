"""Migration 021: sync fishing_meta.week_rewards_json to current WEEK_REWARDS defaults."""

from __future__ import annotations

import json

import aiosqlite

VERSION = 21
DESCRIPTION = (
    "fishing_meta.week_rewards_json — награды/enabled по текущему settings "
    "(12 видов, FoW 1200)"
)

# Зеркало bot/fishing/settings.py WEEK_REWARDS + FISH_OF_WEEK_BONUS
_SPECIES_REWARDS: dict[str, int] = {
    "Карась": 200,
    "Плотва": 250,
    "Окунь": 350,
    "Линь": 450,
    "Язь": 500,
    "Лещ": 450,
    "Сазан": 650,
    "Жерех": 700,
    "Судак": 750,
    "Щука": 700,
    "Сом": 1000,
    "Осётр": 2000,
}
_FISH_OF_WEEK_BONUS = 1200


async def upgrade(conn: aiosqlite.Connection) -> None:
    cur = await conn.execute("PRAGMA table_info(fishing_meta)")
    cols = {str(row[1]) for row in await cur.fetchall()}
    if "week_rewards_json" not in cols:
        await conn.execute(
            "ALTER TABLE fishing_meta ADD COLUMN week_rewards_json TEXT NOT NULL DEFAULT ''"
        )

    await conn.execute(
        "INSERT OR IGNORE INTO fishing_meta "
        "(id, day_key, first_fish_claimed, current_week_id, pending_rewards_week_id, "
        "week_rewards_json) VALUES (1, '', 0, '', '', '')"
    )

    enabled = {name: True for name in _SPECIES_REWARDS}
    # Сохранить уже выключенные виды, если ключ был в старом JSON
    cur = await conn.execute(
        "SELECT week_rewards_json FROM fishing_meta WHERE id = 1"
    )
    row = await cur.fetchone()
    raw = str(row[0] or "").strip() if row else ""
    if raw:
        try:
            old = json.loads(raw)
        except json.JSONDecodeError:
            old = None
        if isinstance(old, dict):
            old_enabled = old.get("enabled")
            if isinstance(old_enabled, dict):
                for name in _SPECIES_REWARDS:
                    if name in old_enabled:
                        enabled[name] = bool(old_enabled[name])

    payload = {
        "species": dict(_SPECIES_REWARDS),
        "fish_of_week_bonus": _FISH_OF_WEEK_BONUS,
        "enabled": enabled,
    }
    await conn.execute(
        "UPDATE fishing_meta SET week_rewards_json = ? WHERE id = 1",
        (json.dumps(payload, ensure_ascii=False),),
    )
    await conn.commit()
