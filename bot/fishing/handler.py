"""Обработчик команд !рыбалка."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from bot.db import Database
from bot.db import fishing as fishing_db
from bot.db import users as users_db
from bot.economy.points import PointsStore
from bot.goodgame import ChatMessage

from . import texts
from .cast import apply_cast_roll, bait_total, consume_bait, roll_worms_dig_outcome
from .events_settings import (
    DEFAULT_BOOST_CASTS,
    GRANT_ITEMS,
    FishingEventsConfig,
    validate_events_payload,
)
from .grants import grant_bite_boost, grant_mermaid_shields, grant_steal_safe
from .record_assets import FISH_RECORD_ASSETS
from .runtime_settings import FishingRuntimeSettings, validate
from .settings import (
    FIRST_FISH_BONUS,
    FISH_OF_WEEK_BONUS,
    FISH_SPECIES,
    FISHING_CMD,
    MERMAID_PENALTY,
    MERMAID_SHIELD_BUY_MAX,
    MERMAID_SHIELD_COST,
    WEEK_REWARDS,
)
from .storage import FishingStorage

if TYPE_CHECKING:
    from bot.web.routes.player import PlayerRoutes

log = logging.getLogger("fishing")

ReplyFn = Callable[[str], Awaitable[None]]
StealAllowedFn = Callable[[], Awaitable[bool]]


class FishingHandler:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._rt = FishingRuntimeSettings.defaults()
        self._rt_is_default = True
        self.store = FishingStorage(db, lambda: self._rt)
        self._reply: Optional[ReplyFn] = None
        self._points: Optional[PointsStore] = None
        self._player: Optional["PlayerRoutes"] = None
        self._steal_allowed: Optional[StealAllowedFn] = None

    async def start(self) -> None:
        await fishing_db.ensure_meta(self._db)
        await self._reload_runtime()
        cal = await self.store.ensure_calendar()
        if await self.store.has_pending_rewards():
            pending = await self.store.pending_week_id()
            _warn_pending_rewards(pending)
        log.info(
            "Fishing модуль запущен (day=%s week=%s, energy_max=%s).",
            cal["meta"]["day_key"],
            cal["meta"]["current_week_id"],
            self._rt.energy_max,
        )

    async def _reload_runtime(self) -> None:
        override = await fishing_db.get_settings_override(self._db)
        self._rt_is_default = override is None
        self._rt = FishingRuntimeSettings.from_override(override)

    async def close(self) -> None:
        pass

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    def bind_obs(self, player: "PlayerRoutes") -> None:
        self._player = player

    def bind_steal_allowed(self, fn: StealAllowedFn) -> None:
        self._steal_allowed = fn

    async def _is_steal_active(self) -> bool:
        if self._steal_allowed is None:
            return False
        return bool(await self._steal_allowed())

    def _require_points(self) -> PointsStore:
        if self._points is None:
            raise RuntimeError("PointsStore not bound")
        return self._points

    async def _push_week_record_overlay(
        self, *, user_name: str, species: str, weight: float
    ) -> None:
        if self._player is None:
            return
        slug = FISH_RECORD_ASSETS.get(species)
        if not slug:
            log.warning("Нет ассета плашки для вида %r", species)
            return
        await self._player.broadcast_fishing_record(
            {
                "action": "fishing_record",
                "kind": "record",
                "userName": user_name,
                "species": species,
                "weight": round(float(weight), 2),
                "imageUrl": f"/assets/fishing/{slug}.png",
            }
        )

    async def _push_mermaid_overlay(
        self, *, user_name: str, loss: int, kind: str = "mermaid"
    ) -> None:
        if self._player is None:
            return
        await self._player.broadcast_fishing_record(
            {
                "action": "fishing_record",
                "kind": kind,
                "userName": user_name,
                "loss": int(loss),
                "imageUrl": "/assets/fishing/rusalka.png",
            }
        )

    async def get_status(self) -> dict:
        await self.store.ensure_calendar()
        meta = await self.store.meta()
        leaders, fow = await self.store.week_top()
        pending = meta.get("pending_rewards_week_id") or ""
        pending_leaders: list = []
        pending_fow = None
        if pending:
            pending_leaders = await self.store.week_leaders(pending)
            pending_fow = await self.store.week_fish_of_week(pending)
        rewards = await self.get_reward_config()
        return {
            "day_key": meta["day_key"],
            "current_week_id": meta["current_week_id"],
            "first_fish_claimed": meta["first_fish_claimed"],
            "pending_rewards_week_id": pending,
            "has_pending_rewards": bool(pending),
            "players": await self.store.count_players(),
            "week_leaders": leaders,
            "fish_of_week": fow,
            "pending_week_leaders": pending_leaders,
            "pending_fish_of_week": pending_fow,
            "week_rewards": rewards["species"],
            "fish_of_week_bonus": rewards["fish_of_week_bonus"],
            "species_enabled": rewards["enabled"],
            "week_rewards_defaults": rewards["defaults"],
            "runtime_settings": self._rt.to_dict(),
            "runtime_settings_defaults": FishingRuntimeSettings.defaults().to_dict(),
            "runtime_settings_is_default": self._rt_is_default,
            "events": (await self.store.load_events_config()).to_dict(),
        }

    def _default_enabled(self) -> dict[str, bool]:
        return {name: True for name in FISH_SPECIES}

    def _default_reward_config(self) -> dict:
        species = {name: int(WEEK_REWARDS.get(name, 0)) for name in FISH_SPECIES}
        fow = int(FISH_OF_WEEK_BONUS)
        enabled = self._default_enabled()
        return {
            "species": species,
            "fish_of_week_bonus": fow,
            "enabled": enabled,
            "defaults": {
                "species": dict(species),
                "fish_of_week_bonus": fow,
                "enabled": dict(enabled),
            },
        }

    def _parse_enabled_map(self, raw: Any, *, base: dict[str, bool]) -> dict[str, bool]:
        out = dict(base)
        if not isinstance(raw, dict):
            return out
        for name in FISH_SPECIES:
            if name not in raw:
                continue
            out[name] = bool(raw[name])
        return out

    async def get_reward_config(self) -> dict:
        base = self._default_reward_config()
        stored = await fishing_db.get_week_rewards_override(self._db)
        if not stored:
            return base
        raw_species = stored.get("species") or {}
        if not isinstance(raw_species, dict):
            raw_species = {}
        species: dict[str, int] = {}
        for name in FISH_SPECIES:
            if name in raw_species:
                try:
                    species[name] = max(0, int(raw_species[name]))
                except (TypeError, ValueError):
                    species[name] = base["species"][name]
            else:
                species[name] = base["species"][name]
        try:
            fow = max(0, int(stored.get("fish_of_week_bonus", base["fish_of_week_bonus"])))
        except (TypeError, ValueError):
            fow = base["fish_of_week_bonus"]
        enabled = self._parse_enabled_map(stored.get("enabled"), base=base["enabled"])
        return {
            "species": species,
            "fish_of_week_bonus": fow,
            "enabled": enabled,
            "defaults": base["defaults"],
        }

    async def get_enabled_species_set(self) -> set[str]:
        cfg = await self.get_reward_config()
        return {name for name, on in cfg["enabled"].items() if on}

    def _normalize_reward_payload(
        self,
        species: Optional[dict],
        fish_of_week_bonus: Optional[int],
        enabled: Optional[dict] = None,
    ) -> tuple[dict[str, int], int, dict[str, bool]]:
        base = self._default_reward_config()
        out_species = dict(base["species"])
        if isinstance(species, dict):
            for name in FISH_SPECIES:
                if name not in species:
                    continue
                try:
                    out_species[name] = max(0, int(species[name]))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"bad_reward:{name}") from exc
        fow = base["fish_of_week_bonus"]
        if fish_of_week_bonus is not None:
            try:
                fow = max(0, int(fish_of_week_bonus))
            except (TypeError, ValueError) as exc:
                raise ValueError("bad_fow_bonus") from exc
        out_enabled = dict(base["enabled"])
        if enabled is not None:
            out_enabled = self._parse_enabled_map(enabled, base=out_enabled)
        return out_species, fow, out_enabled

    async def admin_set_week_rewards(
        self,
        *,
        species: Optional[dict] = None,
        fish_of_week_bonus: Optional[int] = None,
        enabled: Optional[dict] = None,
    ) -> dict:
        out_species, fow, out_enabled = self._normalize_reward_payload(
            species, fish_of_week_bonus, enabled
        )
        await fishing_db.set_week_rewards_override(
            self._db,
            species=out_species,
            fish_of_week_bonus=fow,
            enabled=out_enabled,
        )
        status = await self.get_status()
        return status

    async def admin_set_runtime_settings(self, payload: dict) -> dict:
        validated = validate(payload)
        await fishing_db.set_settings_override(self._db, validated.to_dict())
        self._rt = validated
        self._rt_is_default = False
        log.info("Fishing runtime settings updated: %s", validated.to_dict())
        return await self.get_status()

    async def admin_reset_runtime_settings(self) -> dict:
        await fishing_db.set_settings_override(self._db, None)
        self._rt = FishingRuntimeSettings.defaults()
        self._rt_is_default = True
        log.info("Fishing runtime settings reset to defaults")
        return await self.get_status()

    async def admin_get_events(self) -> dict:
        cfg = await self.store.load_events_config()
        log_rows = await fishing_db.list_grant_log(self._db, limit=100)
        return {
            "schedule": cfg.to_dict(),
            "schedule_defaults": FishingEventsConfig.defaults().to_dict(),
            "grant_log": log_rows,
        }

    async def admin_set_events_schedule(self, payload: dict) -> dict:
        validated = validate_events_payload(payload)
        await fishing_db.set_events_override(self._db, validated)
        log.info("Fishing events schedule updated: %s", validated)
        return await self.admin_get_events()

    async def admin_grant(
        self,
        *,
        user_ids: list[str],
        item: str,
        amount: Optional[int] = None,
    ) -> dict:
        item_key = str(item or "").strip()
        if item_key not in GRANT_ITEMS:
            raise ValueError("item")
        ids = [str(u).strip() for u in user_ids if str(u).strip()]
        if not ids:
            raise ValueError("user_ids")

        if item_key == "mermaid_shield":
            qty = 1 if amount is None else int(amount)
            if qty < 1:
                raise ValueError("amount")
        elif item_key == "bite_boost":
            qty = DEFAULT_BOOST_CASTS if amount is None else int(amount)
            if qty < 0:
                raise ValueError("amount")
        else:
            qty = 1

        log_ids: list[int] = []
        for uid in ids:
            name = await users_db.get_user_name(self._db, uid)
            if item_key == "mermaid_shield":
                await grant_mermaid_shields(
                    self._db, uid, amount=qty, user_name=name
                )
            elif item_key == "bite_boost":
                await grant_bite_boost(
                    self._db, uid, casts=qty, user_name=name
                )
            else:
                await grant_steal_safe(self._db, uid, user_name=name)
            lid = await fishing_db.insert_grant_log(
                self._db,
                user_id=uid,
                user_name=name,
                item=item_key,
                amount=qty,
                actor="admin",
            )
            log_ids.append(lid)

        result = await self.admin_get_events()
        result["granted"] = len(log_ids)
        result["log_ids"] = log_ids
        return result

    async def admin_restore_energy(self, *, announce: bool = True) -> dict:
        n = await self.store.restore_all_energy()
        log.info("Fishing: energy restored for %s players", n)
        if announce:
            await self._say(texts.pick(texts.ADMIN_ENERGY_CHAT))
        status = await self.get_status()
        status["restored"] = n
        return status

    async def admin_pay_week_rewards(
        self,
        *,
        announce: bool = True,
        species: Optional[dict] = None,
        fish_of_week_bonus: Optional[int] = None,
        enabled: Optional[dict] = None,
        persist: bool = True,
    ) -> dict:
        points = self._require_points()
        await self.store.ensure_calendar()
        pending = await self.store.pending_week_id()
        if not pending:
            raise RuntimeError("nothing_to_pay")

        if species is not None or fish_of_week_bonus is not None or enabled is not None:
            reward_species, fow_bonus_cfg, out_enabled = self._normalize_reward_payload(
                species, fish_of_week_bonus, enabled
            )
            if persist:
                await fishing_db.set_week_rewards_override(
                    self._db,
                    species=reward_species,
                    fish_of_week_bonus=fow_bonus_cfg,
                    enabled=out_enabled,
                )
        else:
            cfg = await self.get_reward_config()
            reward_species = cfg["species"]
            fow_bonus_cfg = cfg["fish_of_week_bonus"]

        leaders = await self.store.week_leaders(pending)
        fow = await self.store.week_fish_of_week(pending)
        if not leaders and fow is None:
            await self.store.clear_pending_rewards()
            raise RuntimeError("nothing_to_pay")

        payouts: dict[str, int] = {}
        details: list[dict] = []
        for row in leaders:
            reward = int(reward_species.get(row["species"], 0))
            if reward <= 0:
                continue
            uid = row["user_id"]
            payouts[uid] = payouts.get(uid, 0) + reward
            details.append(
                {
                    "species": row["species"],
                    "user_id": uid,
                    "user_name": row["user_name"],
                    "weight": row["weight"],
                    "reward": reward,
                }
            )

        fow_bonus = 0
        if fow is not None and fow_bonus_cfg > 0:
            fow_bonus = fow_bonus_cfg
            uid = fow["user_id"]
            payouts[uid] = payouts.get(uid, 0) + fow_bonus

        for uid, amount in payouts.items():
            await points.add(uid, amount)
        await points.flush()
        await self.store.clear_pending_rewards()

        if announce:
            msg = texts.format_week_rewards_announce(
                details=details,
                fow=fow,
                fow_bonus=fow_bonus,
                payouts=payouts,
            )
            await self._say(msg)

        status = await self.get_status()
        status["paid_week"] = pending
        status["payouts"] = [
            {"user_id": uid, "amount": amount} for uid, amount in payouts.items()
        ]
        status["details"] = details
        status["fish_of_week_bonus_paid"] = fow_bonus
        status["fish_of_week"] = fow
        return status

    async def handle_message(self, msg: ChatMessage) -> bool:
        text = msg.text.strip()
        lower = text.lower()
        if not lower.startswith(FISHING_CMD):
            return False

        rest = text[len(FISHING_CMD) :].strip()
        sub = rest.split(maxsplit=1)[0].lower() if rest else ""

        cal = await self.store.ensure_calendar()
        prefix_note = ""
        if cal["day_changed"]:
            prefix_note = texts.pick(texts.BAIT_SPOILED) + " "
            events = await self.store.load_events_config()
            if events.is_active_today():
                prefix_note += (
                    texts.pick(texts.EVENT_BOOST_DAY).format(N=events.boost_casts)
                    + " "
                )

        # Любая !рыбалка* — ленивая выдача ивент-буста (тихо, 1 раз/сутки).
        await self.store.get_or_create_player(msg.user_id, msg.user_name)

        if not rest:
            await self._cmd_cast(msg, prefix_note)
            return True
        if sub == "черви":
            await self._cmd_worms(msg, prefix_note)
            return True
        if sub == "опарыш":
            await self._cmd_maggot(msg, prefix_note)
            return True
        if sub == "удочка":
            await self._cmd_rod(msg, prefix_note)
            return True
        if sub == "защита":
            await self._cmd_shield(msg, prefix_note, rest)
            return True
        if sub == "помощь":
            await self._say(
                f"{msg.user_name}, "
                f"{texts.pick(texts.HELP).format(N=FIRST_FISH_BONUS, C=self._rt.maggot_cost)}"
            )
            return True
        if sub == "энергия":
            await self._cmd_energy(msg)
            return True
        if sub == "улов":
            await self._cmd_catch(msg)
            return True
        if sub == "топрыба":
            await self._cmd_top(msg)
            return True

        await self._say(
            f"{msg.user_name}, неизвестная подкоманда. "
            f"{texts.pick(texts.HELP).format(N=FIRST_FISH_BONUS, C=self._rt.maggot_cost)}"
        )
        return True

    async def _cmd_cast(self, msg: ChatMessage, prefix_note: str) -> None:
        points = self._require_points()
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        now = time.time()
        rt = self._rt

        if player["rod_state"] != fishing_db.ROD_OK:
            await self._say(f"{msg.user_name}, {prefix_note}{texts.pick(texts.DENY_NO_ROD)}")
            return
        if bait_total(player) < 1:
            await self._say(f"{msg.user_name}, {prefix_note}{texts.pick(texts.DENY_NO_BAIT)}")
            return
        if player["energy"] < rt.cast_energy_cost:
            body = texts.pick(texts.DENY_NO_ENERGY).replace("{X}", str(player["energy"]))
            await self._say(f"{msg.user_name}, {prefix_note}{body}")
            return
        if now - float(player["last_cast_at"]) < rt.cast_cooldown_sec:
            await self._say(f"{msg.user_name}, {prefix_note}{texts.pick(texts.DENY_COOLDOWN)}")
            return

        player["energy"] -= rt.cast_energy_cost
        consume_bait(player, 1)
        player["last_cast_at"] = now

        balance = await points.get_balance(msg.user_id)
        enabled = await self.get_enabled_species_set()
        result, delta = apply_cast_roll(
            player,
            points_balance=balance,
            enabled_species=enabled,
            miss_chance=rt.miss_chance,
            trash_chance=rt.trash_chance,
            bite_boost_miss_trash_div=rt.bite_boost_miss_trash_div,
        )

        if result.kind == "fish" and result.species and result.weight is not None:
            if await self.store.claim_first_fish():
                result.first_fish = True
                delta += FIRST_FISH_BONUS
                result.message += " " + texts.pick(texts.FIRST_FISH).format(
                    N=FIRST_FISH_BONUS
                )
            flags = await self.store.update_records(
                user_id=msg.user_id,
                user_name=msg.user_name,
                species=result.species,
                weight=result.weight,
            )
            weight_s = f"{result.weight:.2f}"
            if flags.get("week_species_record"):
                result.message += " " + texts.pick(texts.WEEK_SPECIES_RECORD).format(
                    species=result.species,
                    species_lower=result.species.lower(),
                    weight=weight_s,
                )
                await self._push_week_record_overlay(
                    user_name=msg.user_name,
                    species=result.species,
                    weight=float(result.weight),
                )
            if flags.get("fish_of_week"):
                result.message += " " + texts.pick(texts.WEEK_FISH_OF_WEEK).format(
                    species=result.species,
                    weight=weight_s,
                )
        elif result.kind == "mermaid":
            await self._push_mermaid_overlay(
                user_name=msg.user_name,
                loss=-delta if delta < 0 else MERMAID_PENALTY,
                kind="mermaid",
            )
        elif result.kind == "mermaid_blocked":
            await self._push_mermaid_overlay(
                user_name=msg.user_name,
                loss=0,
                kind="mermaid_blocked",
            )

        if delta != 0:
            await points.add(msg.user_id, delta)
            await points.flush()

        await self.store.save_player(player)
        res_line = texts.resources_from_player(player)
        await self._say(
            f"{msg.user_name}, {prefix_note}{result.message}\n{res_line}"
        )

    async def _cmd_worms(self, msg: ChatMessage, prefix_note: str) -> None:
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        rt = self._rt
        if player["energy"] < rt.worms_energy_cost:
            body = texts.pick(texts.WORMS_NO_ENERGY).replace("{X}", str(player["energy"]))
            await self._say(f"{msg.user_name}, {prefix_note}{body}")
            return
        player["energy"] -= rt.worms_energy_cost
        steal_active = await self._is_steal_active()
        outcome = roll_worms_dig_outcome(
            steal_active=steal_active,
            shield_chance=rt.worms_dig_shield_chance,
            bite_chance=rt.worms_dig_bite_chance,
            safe_chance=rt.worms_dig_safe_chance,
        )
        if outcome == "shield":
            player["mermaid_shields"] = int(player.get("mermaid_shields") or 0) + 1
            body = texts.pick(texts.WORMS_DIG_SHIELD).format(
                S=player["mermaid_shields"]
            )
        elif outcome == "bite":
            player["bite_boost_casts_left"] = (
                int(player.get("bite_boost_casts_left") or 0) + rt.bite_boost_casts
            )
            body = texts.pick(texts.WORMS_DIG_BITE).format(
                B=rt.bite_boost_casts,
                T=player["bite_boost_casts_left"],
            )
        elif outcome == "safe":
            already = bool(player.get("steal_safe"))
            player["steal_safe"] = True
            pool = texts.WORMS_DIG_SAFE_ALREADY if already else texts.WORMS_DIG_SAFE
            body = texts.pick(pool)
        else:
            player["worms"] += rt.worms_gain
            body = texts.pick(texts.WORMS_OK)
        await self.store.save_player(player)
        res = texts.resources_from_player(player)
        await self._say(f"{msg.user_name}, {prefix_note}{body}\n{res}")

    async def _cmd_maggot(self, msg: ChatMessage, prefix_note: str) -> None:
        points = self._require_points()
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        rt = self._rt
        balance = await points.get_balance(msg.user_id)
        if balance < rt.maggot_cost:
            await self._say(
                f"{msg.user_name}, {prefix_note}"
                f"{texts.pick(texts.MAGGOT_NO_POINTS).format(C=rt.maggot_cost)}"
            )
            return
        await points.add(msg.user_id, -rt.maggot_cost)
        await points.flush()
        player["maggots"] += rt.maggot_gain
        await self.store.save_player(player)
        res = texts.resources_from_player(player)
        await self._say(
            f"{msg.user_name}, {prefix_note}"
            f"{texts.pick(texts.MAGGOT_OK).format(C=rt.maggot_cost, G=rt.maggot_gain)}\n{res}"
        )

    async def _cmd_rod(self, msg: ChatMessage, prefix_note: str) -> None:
        points = self._require_points()
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        if player["rod_state"] == fishing_db.ROD_OK:
            await self._say(
                f"{msg.user_name}, {prefix_note}{texts.pick(texts.ROD_ALREADY)}"
            )
            return
        balance = await points.get_balance(msg.user_id)
        if balance < self._rt.rod_cost:
            await self._say(
                f"{msg.user_name}, {prefix_note}{texts.pick(texts.ROD_NO_POINTS)}"
            )
            return
        await points.add(msg.user_id, -self._rt.rod_cost)
        await points.flush()
        player["rod_state"] = fishing_db.ROD_OK
        await self.store.save_player(player)
        res = texts.resources_from_player(player)
        await self._say(
            f"{msg.user_name}, {prefix_note}{texts.pick(texts.ROD_OK)}\n{res}"
        )

    async def _cmd_shield(
        self, msg: ChatMessage, prefix_note: str, rest: str
    ) -> None:
        points = self._require_points()
        parts = rest.split()
        qty = 1
        if len(parts) >= 2:
            try:
                qty = int(parts[1])
            except ValueError:
                await self._say(
                    f"{msg.user_name}, {prefix_note}"
                    f"{texts.pick(texts.SHIELD_BAD_QTY).format(MAX=MERMAID_SHIELD_BUY_MAX)}"
                )
                return
        if qty < 1 or qty > MERMAID_SHIELD_BUY_MAX:
            await self._say(
                f"{msg.user_name}, {prefix_note}"
                f"{texts.pick(texts.SHIELD_BAD_QTY).format(MAX=MERMAID_SHIELD_BUY_MAX)}"
            )
            return

        cost = MERMAID_SHIELD_COST * qty
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        balance = await points.get_balance(msg.user_id)
        if balance < cost:
            await self._say(
                f"{msg.user_name}, {prefix_note}"
                f"{texts.pick(texts.SHIELD_NO_POINTS).format(C=MERMAID_SHIELD_COST, N=qty)}"
            )
            return
        await points.add(msg.user_id, -cost)
        await points.flush()
        player["mermaid_shields"] = int(player.get("mermaid_shields") or 0) + qty
        await self.store.save_player(player)
        res = texts.resources_from_player(player)
        await self._say(
            f"{msg.user_name}, {prefix_note}"
            f"{texts.pick(texts.SHIELD_OK).format(N=qty, C=cost, S=player['mermaid_shields'])}\n{res}"
        )

    async def _cmd_energy(self, msg: ChatMessage) -> None:
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        body = texts.pick(texts.ENERGY_CARD).format(
            E=player["energy"],
            W=player["worms"],
            M=player["maggots"],
            rod=texts.rod_label(player["rod_state"]),
            rod_hint=texts.rod_hint(player["rod_state"]),
            S=int(player.get("mermaid_shields") or 0),
            B=int(player.get("bite_boost_casts_left") or 0),
            SAFE=texts.safe_label(bool(player.get("steal_safe"))),
        )
        await self._say(f"{msg.user_name}, {body}")

    async def _cmd_catch(self, msg: ChatMessage) -> None:
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        records = await self.store.list_records(msg.user_id)
        res = texts.resources_from_player(player)
        if not records:
            await self._say(
                f"{msg.user_name}, Пока без рекордов по видам. Запасы: {res}."
            )
            return
        parts = ", ".join(f"{sp} — {w:.2f} кг" for sp, w in records)
        await self._say(f"{msg.user_name}, Твои рекорды: {parts}. {res}.")

    async def _cmd_top(self, msg: ChatMessage) -> None:
        leaders, fow = await self.store.week_top()
        if not leaders:
            await self._say(
                f"{msg.user_name}, Недельный топ пока пуст. Лови рыбу — и займи место!"
            )
            return
        leader_bits = [
            f"{r['species']} — {r['user_name'] or r['user_id']} ({r['weight']:.2f} кг)"
            for r in leaders
        ]
        leaders_str = ", ".join(leader_bits)
        fow_name = (fow["user_name"] if fow else "—") or "—"
        fow_weight = f"{fow['weight']:.2f}" if fow else "—"
        body = texts.pick(texts.TOP_WEEK).format(
            leaders=leaders_str,
            fow_name=fow_name,
            fow_weight=fow_weight,
        )
        await self._say(f"{msg.user_name}, {body}")

    async def _say(self, text: str) -> None:
        if self._reply is None:
            log.warning("Fishing reply not bound: %s", text)
            return
        await self._reply(text)


def _warn_pending_rewards(week_id: str) -> None:
    """Яркое предупреждение в консоль при старте."""
    red = "\033[91m"
    bold = "\033[1m"
    reset = "\033[0m"
    msg = (
        f"{bold}{red}⚠ Рыбалка: награды недели ещё не выданы "
        f"(неделя {week_id}). Выдайте в admin.html, когда будете на эфире.{reset}"
    )
    print(msg)
    log.warning("Fishing pending week rewards: %s", week_id)
