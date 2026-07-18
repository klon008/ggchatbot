"""Тонкая обёртка над bot.db.fishing + календарь суток/недели."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from bot.db import Database
from bot.db import fishing as fishing_db

from .economy import apply_energy_regen, day_key, new_player, week_id
from .settings import ENERGY_MAX

log = logging.getLogger("fishing")


class FishingStorage:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def ensure_calendar(self) -> dict[str, Any]:
        """Синхронизировать сутки/неделю. Возвращает флаги day_changed / week_changed."""
        meta = await fishing_db.get_meta(self._db)
        today = day_key()
        this_week = week_id()
        day_changed = False
        week_changed = False
        now_ts = time.time()

        if meta["day_key"] != today:
            if meta["day_key"]:
                day_changed = True
                await fishing_db.reset_all_for_new_day(
                    self._db,
                    energy=ENERGY_MAX,
                    energy_updated_at=now_ts,
                    day_key=today,
                )
                log.info("Fishing day reset: %s → %s", meta["day_key"], today)
            await fishing_db.set_meta(
                self._db,
                day_key=today,
                first_fish_claimed=False,
            )
            meta["day_key"] = today
            meta["first_fish_claimed"] = False

        if meta["current_week_id"] != this_week:
            old = meta["current_week_id"]
            if old:
                week_changed = True
                pending = meta["pending_rewards_week_id"]
                if not pending:
                    await fishing_db.set_meta(
                        self._db,
                        pending_rewards_week_id=old,
                    )
                    meta["pending_rewards_week_id"] = old
                    log.info("Fishing week closed, pending rewards: %s", old)
            await fishing_db.set_meta(self._db, current_week_id=this_week)
            meta["current_week_id"] = this_week
            log.info("Fishing week: %s → %s", old or "(none)", this_week)

        return {
            "meta": meta,
            "day_changed": day_changed,
            "week_changed": week_changed,
        }

    async def get_or_create_player(self, user_id: str, user_name: str) -> dict[str, Any]:
        await self.ensure_calendar()
        player = await fishing_db.get_player(self._db, user_id)
        now_ts = time.time()
        today = day_key()
        if player is None:
            player = new_player(user_id, user_name, now_ts)
            player["day_key"] = today
            await fishing_db.upsert_player(self._db, player)
            return player
        player["user_name"] = user_name
        apply_energy_regen(player, now_ts)
        if player.get("day_key") != today:
            # На случай если игрок пропустил глобальный ресет (не было в таблице)
            player["energy"] = ENERGY_MAX
            player["energy_updated_at"] = now_ts
            player["worms"] = 0
            player["maggots"] = 0
            player["day_key"] = today
        await fishing_db.upsert_player(self._db, player)
        return player

    async def save_player(self, player: dict[str, Any]) -> None:
        await fishing_db.upsert_player(self._db, player)

    async def meta(self) -> dict[str, Any]:
        return await fishing_db.get_meta(self._db)

    async def claim_first_fish(self) -> bool:
        """Атомарно забрать «первую рыбу дня». True если бонус наш."""
        return await fishing_db.claim_first_fish(self._db)

    async def update_records(
        self,
        *,
        user_id: str,
        user_name: str,
        species: str,
        weight: float,
    ) -> dict[str, bool]:
        """Обновить личные и недельные рекорды. Возвращает флаги для чата."""
        personal_best = await fishing_db.set_record_if_better(
            self._db, user_id, species, weight
        )
        meta = await fishing_db.get_meta(self._db)
        week = meta["current_week_id"] or week_id()
        prev_leader = await fishing_db.get_week_species_leader(self._db, week, species)
        week_species_record = prev_leader is None or float(weight) > float(
            prev_leader["weight"]
        )
        await fishing_db.set_week_weight_if_better(
            self._db,
            week_id=week,
            user_id=user_id,
            user_name=user_name,
            species=species,
            weight=weight,
            achieved_at=time.time(),
        )
        fow = await fishing_db.week_fish_of_week(self._db, week)
        fish_of_week = bool(
            fow
            and str(fow["user_id"]) == str(user_id)
            and fow["species"] == species
            and abs(float(fow["weight"]) - float(weight)) < 1e-9
        )
        return {
            "personal_best": personal_best,
            "week_species_record": week_species_record,
            "fish_of_week": fish_of_week,
        }

    async def list_records(self, user_id: str) -> list[tuple[str, float]]:
        return await fishing_db.list_records(self._db, user_id)

    async def week_top(self, week: Optional[str] = None) -> tuple[list[dict], Optional[dict]]:
        meta = await fishing_db.get_meta(self._db)
        wid = week or meta["current_week_id"] or week_id()
        leaders = await fishing_db.week_leaders(self._db, wid)
        fow = await fishing_db.week_fish_of_week(self._db, wid)
        return leaders, fow

    async def restore_all_energy(self) -> int:
        return await fishing_db.restore_all_energy(
            self._db,
            energy=ENERGY_MAX,
            energy_updated_at=time.time(),
        )

    async def pending_week_id(self) -> str:
        meta = await fishing_db.get_meta(self._db)
        return str(meta.get("pending_rewards_week_id") or "")

    async def clear_pending_rewards(self) -> None:
        await fishing_db.set_meta(self._db, pending_rewards_week_id="")

    async def week_leaders(self, week_id_str: str) -> list[dict[str, Any]]:
        return await fishing_db.week_leaders(self._db, week_id_str)

    async def week_fish_of_week(self, week_id_str: str) -> Optional[dict[str, Any]]:
        return await fishing_db.week_fish_of_week(self._db, week_id_str)

    async def count_players(self) -> int:
        return await fishing_db.count_players(self._db)

    async def has_pending_rewards(self) -> bool:
        return bool(await self.pending_week_id())
