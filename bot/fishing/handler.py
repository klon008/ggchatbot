"""Обработчик команд !рыбалка."""

from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable, Optional

from bot.db import Database
from bot.db import fishing as fishing_db
from bot.economy.points import PointsStore
from bot.goodgame import ChatMessage

from . import texts
from .cast import apply_cast_roll, bait_total, consume_bait
from .settings import (
    CAST_COOLDOWN_SEC,
    CAST_ENERGY_COST,
    FIRST_FISH_BONUS,
    FISH_OF_WEEK_BONUS,
    FISH_SPECIES,
    FISHING_CMD,
    MAGGOT_COST,
    MAGGOT_GAIN,
    ROD_COST,
    WEEK_REWARDS,
    WORMS_ENERGY_COST,
    WORMS_GAIN,
)
from .storage import FishingStorage

log = logging.getLogger("fishing")

ReplyFn = Callable[[str], Awaitable[None]]


class FishingHandler:
    def __init__(self, db: Database) -> None:
        self._db = db
        self.store = FishingStorage(db)
        self._reply: Optional[ReplyFn] = None
        self._points: Optional[PointsStore] = None

    async def start(self) -> None:
        await fishing_db.ensure_meta(self._db)
        cal = await self.store.ensure_calendar()
        if await self.store.has_pending_rewards():
            pending = await self.store.pending_week_id()
            _warn_pending_rewards(pending)
        log.info(
            "Fishing модуль запущен (day=%s week=%s).",
            cal["meta"]["day_key"],
            cal["meta"]["current_week_id"],
        )

    async def close(self) -> None:
        pass

    def bind_reply(self, reply: ReplyFn) -> None:
        self._reply = reply

    def bind_points(self, store: PointsStore) -> None:
        self._points = store

    def _require_points(self) -> PointsStore:
        if self._points is None:
            raise RuntimeError("PointsStore not bound")
        return self._points

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
            "week_rewards_defaults": rewards["defaults"],
        }

    def _default_reward_config(self) -> dict:
        species = {name: int(WEEK_REWARDS.get(name, 0)) for name in FISH_SPECIES}
        fow = int(FISH_OF_WEEK_BONUS)
        return {
            "species": species,
            "fish_of_week_bonus": fow,
            "defaults": {
                "species": dict(species),
                "fish_of_week_bonus": fow,
            },
        }

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
        return {
            "species": species,
            "fish_of_week_bonus": fow,
            "defaults": base["defaults"],
        }

    def _normalize_reward_payload(
        self,
        species: Optional[dict],
        fish_of_week_bonus: Optional[int],
    ) -> tuple[dict[str, int], int]:
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
        return out_species, fow

    async def admin_set_week_rewards(
        self,
        *,
        species: Optional[dict] = None,
        fish_of_week_bonus: Optional[int] = None,
    ) -> dict:
        out_species, fow = self._normalize_reward_payload(species, fish_of_week_bonus)
        await fishing_db.set_week_rewards_override(
            self._db,
            species=out_species,
            fish_of_week_bonus=fow,
        )
        status = await self.get_status()
        return status

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
        persist: bool = True,
    ) -> dict:
        points = self._require_points()
        await self.store.ensure_calendar()
        pending = await self.store.pending_week_id()
        if not pending:
            raise RuntimeError("nothing_to_pay")

        if species is not None or fish_of_week_bonus is not None:
            reward_species, fow_bonus_cfg = self._normalize_reward_payload(
                species, fish_of_week_bonus
            )
            if persist:
                await fishing_db.set_week_rewards_override(
                    self._db,
                    species=reward_species,
                    fish_of_week_bonus=fow_bonus_cfg,
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
            if fow is not None:
                msg = texts.pick(texts.ADMIN_REWARDS_CHAT).format(
                    name=fow["user_name"] or fow["user_id"],
                    species=fow["species"],
                    weight=f"{fow['weight']:.2f}",
                )
            else:
                msg = "Неделя закрыта: награды вручены. Кто в новом топе — решение за клёвом!"
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
        if sub == "помощь":
            await self._say(
                f"{msg.user_name}, "
                f"{texts.pick(texts.HELP).format(N=FIRST_FISH_BONUS, C=MAGGOT_COST)}"
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
            f"{texts.pick(texts.HELP).format(N=FIRST_FISH_BONUS, C=MAGGOT_COST)}"
        )
        return True

    async def _cmd_cast(self, msg: ChatMessage, prefix_note: str) -> None:
        points = self._require_points()
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        now = time.time()

        if player["rod_state"] != fishing_db.ROD_OK:
            await self._say(f"{msg.user_name}, {prefix_note}{texts.pick(texts.DENY_NO_ROD)}")
            return
        if bait_total(player) < 1:
            await self._say(f"{msg.user_name}, {prefix_note}{texts.pick(texts.DENY_NO_BAIT)}")
            return
        if player["energy"] < CAST_ENERGY_COST:
            body = texts.pick(texts.DENY_NO_ENERGY).replace("{X}", str(player["energy"]))
            await self._say(f"{msg.user_name}, {prefix_note}{body}")
            return
        if now - float(player["last_cast_at"]) < CAST_COOLDOWN_SEC:
            await self._say(f"{msg.user_name}, {prefix_note}{texts.pick(texts.DENY_COOLDOWN)}")
            return

        player["energy"] -= CAST_ENERGY_COST
        consume_bait(player, 1)
        player["last_cast_at"] = now

        balance = await points.get_balance(msg.user_id)
        result, delta = apply_cast_roll(player, points_balance=balance)

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
            if flags.get("fish_of_week"):
                result.message += " " + texts.pick(texts.WEEK_FISH_OF_WEEK).format(
                    species=result.species,
                    weight=weight_s,
                )

        if delta != 0:
            await points.add(msg.user_id, delta)
            await points.flush()

        await self.store.save_player(player)
        res_line = texts.format_resources(
            player["energy"], player["worms"], player["maggots"], player["rod_state"]
        )
        await self._say(
            f"{msg.user_name}, {prefix_note}{result.message}\n{res_line}"
        )

    async def _cmd_worms(self, msg: ChatMessage, prefix_note: str) -> None:
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        if player["energy"] < WORMS_ENERGY_COST:
            body = texts.pick(texts.WORMS_NO_ENERGY).replace("{X}", str(player["energy"]))
            await self._say(f"{msg.user_name}, {prefix_note}{body}")
            return
        player["energy"] -= WORMS_ENERGY_COST
        player["worms"] += WORMS_GAIN
        await self.store.save_player(player)
        res = texts.format_resources(
            player["energy"], player["worms"], player["maggots"], player["rod_state"]
        )
        await self._say(
            f"{msg.user_name}, {prefix_note}{texts.pick(texts.WORMS_OK)}\n{res}"
        )

    async def _cmd_maggot(self, msg: ChatMessage, prefix_note: str) -> None:
        points = self._require_points()
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        balance = await points.get_balance(msg.user_id)
        if balance < MAGGOT_COST:
            await self._say(
                f"{msg.user_name}, {prefix_note}"
                f"{texts.pick(texts.MAGGOT_NO_POINTS).format(C=MAGGOT_COST)}"
            )
            return
        await points.add(msg.user_id, -MAGGOT_COST)
        await points.flush()
        player["maggots"] += MAGGOT_GAIN
        await self.store.save_player(player)
        res = texts.format_resources(
            player["energy"], player["worms"], player["maggots"], player["rod_state"]
        )
        await self._say(
            f"{msg.user_name}, {prefix_note}"
            f"{texts.pick(texts.MAGGOT_OK).format(C=MAGGOT_COST, G=MAGGOT_GAIN)}\n{res}"
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
        if balance < ROD_COST:
            await self._say(
                f"{msg.user_name}, {prefix_note}{texts.pick(texts.ROD_NO_POINTS)}"
            )
            return
        await points.add(msg.user_id, -ROD_COST)
        await points.flush()
        player["rod_state"] = fishing_db.ROD_OK
        await self.store.save_player(player)
        res = texts.format_resources(
            player["energy"], player["worms"], player["maggots"], player["rod_state"]
        )
        await self._say(
            f"{msg.user_name}, {prefix_note}{texts.pick(texts.ROD_OK)}\n{res}"
        )

    async def _cmd_energy(self, msg: ChatMessage) -> None:
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        body = texts.pick(texts.ENERGY_CARD).format(
            E=player["energy"],
            W=player["worms"],
            M=player["maggots"],
            rod=texts.rod_label(player["rod_state"]),
            rod_hint=texts.rod_hint(player["rod_state"]),
        )
        await self._say(f"{msg.user_name}, {body}")

    async def _cmd_catch(self, msg: ChatMessage) -> None:
        player = await self.store.get_or_create_player(msg.user_id, msg.user_name)
        records = await self.store.list_records(msg.user_id)
        res = (
            f"Энергия: {player['energy']}/100, Черви: {player['worms']}, "
            f"Опарыш: {player['maggots']}, Удочка: {texts.rod_label(player['rod_state'])}"
        )
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
