"""Алгоритм заброса: негатив / сход / мусор / рыба."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional

from .economy import sell_price
from .settings import (
    BITE_BOOST_MISS_TRASH_DIV,
    FISH_SPECIES,
    MERMAID_PENALTY,
    MISS_CHANCE,
    NEG_EVENT_CHANCES,
    SEAGULL_BAIT_MAX,
    SILT_ENERGY_LOSS,
    TRASH_CHANCE,
    TRASH_TYPES,
    WORMS_DIG_BITE_CHANCE,
    WORMS_DIG_SAFE_CHANCE,
    WORMS_DIG_SHIELD_CHANCE,
)
from . import texts


@dataclass
class CastResult:
    kind: str  # fish | miss | trash | mermaid | mermaid_blocked | pike_break | seagull | silt | reeds
    message: str
    sale: int = 0
    first_fish: bool = False
    species: Optional[str] = None
    weight: Optional[float] = None
    size: Optional[str] = None
    bait_taken: int = 0


def _roll_neg_event() -> Optional[str]:
    roll = random.random()
    acc = 0.0
    for name, chance in NEG_EVENT_CHANCES.items():
        acc += chance
        if roll < acc:
            return name
    return None


def _pick_species(enabled: Optional[set[str]] = None) -> Optional[str]:
    names = [
        n
        for n in FISH_SPECIES
        if enabled is None or n in enabled
    ]
    if not names:
        return None
    weights = [FISH_SPECIES[n][0] for n in names]
    return random.choices(names, weights=weights, k=1)[0]


def _roll_weight(species: str) -> float:
    _, w_min, w_max, _ = FISH_SPECIES[species]
    return round(random.uniform(w_min, w_max), 2)


def consume_bait(player: dict[str, Any], amount: int = 1) -> int:
    """Списать наживку: сначала черви, потом опарыш. Возвращает сколько списано."""
    left = amount
    take_worms = min(player["worms"], left)
    player["worms"] -= take_worms
    left -= take_worms
    if left > 0:
        take_maggots = min(player["maggots"], left)
        player["maggots"] -= take_maggots
        left -= take_maggots
    return amount - left


def bait_total(player: dict[str, Any]) -> int:
    return int(player["worms"]) + int(player["maggots"])


def roll_worms_dig_outcome(
    *,
    steal_active: bool = False,
    shield_chance: float | None = None,
    bite_chance: float | None = None,
    safe_chance: float | None = None,
) -> str:
    """Исход копания: shield | bite | safe | worms (взаимоисключающие).

    safe только если steal_active (команда !кража сейчас доступна).
    """
    dig_shield = (
        WORMS_DIG_SHIELD_CHANCE if shield_chance is None else float(shield_chance)
    )
    dig_bite = WORMS_DIG_BITE_CHANCE if bite_chance is None else float(bite_chance)
    dig_safe = WORMS_DIG_SAFE_CHANCE if safe_chance is None else float(safe_chance)
    roll = random.random()
    if roll < dig_shield:
        return "shield"
    acc = dig_shield
    if roll < acc + dig_bite:
        return "bite"
    acc += dig_bite
    if steal_active and roll < acc + dig_safe:
        return "safe"
    return "worms"


def apply_cast_roll(
    player: dict[str, Any],
    *,
    points_balance: int,
    with_prefix: bool = True,
    enabled_species: Optional[set[str]] = None,
    miss_chance: float | None = None,
    trash_chance: float | None = None,
    bite_boost_miss_trash_div: int | None = None,
) -> tuple[CastResult, int]:
    """
    Ресурсы заброса уже списаны.
    Возвращает (результат, дельта принцесс: отрицательная = штраф, положительная = продажа без бонуса дня).
    enabled_species: если задан — дроп только из этого множества (пусто → сход вместо рыбы).
    """
    prefix = (texts.pick(texts.CAST_PREFIX) + " ") if with_prefix else ""

    base_miss = MISS_CHANCE if miss_chance is None else float(miss_chance)
    base_trash = TRASH_CHANCE if trash_chance is None else float(trash_chance)
    boost_div = (
        BITE_BOOST_MISS_TRASH_DIV
        if bite_boost_miss_trash_div is None
        else int(bite_boost_miss_trash_div)
    )

    boost_active = int(player.get("bite_boost_casts_left") or 0) > 0
    if boost_active:
        player["bite_boost_casts_left"] = int(player["bite_boost_casts_left"]) - 1
        div = max(1, boost_div)
        roll_miss = base_miss / div
        roll_trash = base_trash / div
    else:
        roll_miss = base_miss
        roll_trash = base_trash

    event = _roll_neg_event()

    if event == "mermaid":
        shields = int(player.get("mermaid_shields") or 0)
        if shields > 0:
            player["mermaid_shields"] = shields - 1
            msg = prefix + texts.pick(texts.NEG_MERMAID_BLOCKED)
            return CastResult(kind="mermaid_blocked", message=msg), 0
        loss = min(MERMAID_PENALTY, points_balance)
        msg = prefix + texts.pick(texts.NEG_MERMAID)
        return CastResult(kind="mermaid", message=msg), -loss

    if event == "pike_break":
        player["rod_state"] = "broken"
        msg = prefix + texts.pick(texts.NEG_PIKE)
        return CastResult(kind="pike_break", message=msg), 0

    if event == "seagull":
        taken = consume_bait(player, min(SEAGULL_BAIT_MAX, bait_total(player)))
        msg = prefix + texts.pick(texts.NEG_SEAGULL).replace("{K}", str(taken))
        return CastResult(kind="seagull", message=msg, bait_taken=taken), 0

    if event == "silt":
        player["energy"] = max(0, int(player["energy"]) - SILT_ENERGY_LOSS)
        msg = prefix + texts.pick(texts.NEG_SILT)
        return CastResult(kind="silt", message=msg), 0

    if event == "reeds":
        msg = prefix + texts.pick(texts.NEG_REEDS)
        return CastResult(kind="reeds", message=msg), 0

    category = random.random()
    if category < roll_miss:
        msg = prefix + texts.pick(texts.MISS)
        return CastResult(kind="miss", message=msg), 0

    if category < roll_miss + roll_trash:
        trash_key = random.choice(TRASH_TYPES)
        msg = prefix + texts.pick(texts.TRASH[trash_key])
        return CastResult(kind="trash", message=msg), 0

    species = _pick_species(enabled_species)
    if species is None:
        msg = prefix + texts.pick(texts.MISS)
        return CastResult(kind="miss", message=msg), 0

    weight = _roll_weight(species)
    size, sale = sell_price(species, weight)
    catch = texts.pick(texts.FISH_CATCH).format(
        species=species,
        species_lower=species.lower(),
        size=size,
        weight=f"{weight:.2f}",
        N=sale,
    )
    if catch.startswith("Ты закидываешь"):
        msg = catch
    else:
        msg = prefix + catch
    return (
        CastResult(
            kind="fish",
            message=msg,
            sale=sale,
            species=species,
            weight=weight,
            size=size,
        ),
        sale,
    )
