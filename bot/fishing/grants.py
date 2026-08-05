"""Публичная выдача дневных расходников рыбалки для других мини-игр.

Без сообщений в чат — вызывающий модуль сам пишет текст.
"""

from __future__ import annotations

from bot.db import fishing as fishing_db
from bot.db.connection import Database

from .runtime_settings import load_runtime
from .storage import FishingStorage


async def grant_mermaid_shields(
    db: Database,
    user_id: str,
    *,
    amount: int = 1,
    user_name: str = "",
) -> int:
    """Добавить одноразовые щиты от русалки. Возвращает новый стек."""
    rt = await load_runtime(db)
    store = FishingStorage(db, lambda: rt)
    await store.ensure_calendar()
    player = await store.get_or_create_player(user_id, user_name or "")
    add = max(0, int(amount))
    player["mermaid_shields"] = int(player.get("mermaid_shields") or 0) + add
    await store.save_player(player)
    return int(player["mermaid_shields"])


async def grant_bite_boost(
    db: Database,
    user_id: str,
    *,
    casts: int | None = None,
    user_name: str = "",
) -> int:
    """Добавить заряды активатора клёва. Возвращает bite_boost_casts_left."""
    rt = await load_runtime(db)
    store = FishingStorage(db, lambda: rt)
    await store.ensure_calendar()
    player = await store.get_or_create_player(user_id, user_name or "")
    add = rt.bite_boost_casts if casts is None else max(0, int(casts))
    player["bite_boost_casts_left"] = (
        int(player.get("bite_boost_casts_left") or 0) + add
    )
    await store.save_player(player)
    return int(player["bite_boost_casts_left"])


async def grant_steal_safe(
    db: Database,
    user_id: str,
    *,
    user_name: str = "",
) -> bool:
    """Включить карманный сейф до конца суток. Возвращает True (сейф активен)."""
    rt = await load_runtime(db)
    store = FishingStorage(db, lambda: rt)
    await store.ensure_calendar()
    player = await store.get_or_create_player(user_id, user_name or "")
    player["steal_safe"] = True
    await store.save_player(player)
    return True


async def has_steal_safe(db: Database, user_id: str) -> bool:
    """Есть ли у игрока карманный сейф сегодня (с учётом дневного сброса)."""
    rt = await load_runtime(db)
    store = FishingStorage(db, lambda: rt)
    await store.ensure_calendar()
    player = await fishing_db.get_player(db, user_id)
    if player is None:
        return False
    return bool(player.get("steal_safe"))
