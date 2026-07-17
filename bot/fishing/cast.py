"""Алгоритм заброса: негатив / мусор / рыба."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional

from .economy import sell_price
from .settings import (
    FISH_SPECIES,
    MERMAID_PENALTY,
    NEG_EVENT_CHANCES,
    SEAGULL_BAIT_MAX,
    SILT_ENERGY_LOSS,
    TRASH_CHANCE,
    TRASH_TYPES,
)
from . import texts


@dataclass
class CastResult:
    kind: str  # fish | trash | mermaid | pike_break | seagull | silt | reeds
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


def _pick_species() -> str:
    names = list(FISH_SPECIES.keys())
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


def apply_cast_roll(
    player: dict[str, Any],
    *,
    points_balance: int,
    with_prefix: bool = True,
) -> tuple[CastResult, int]:
    """
    Ресурсы заброса уже списаны.
    Возвращает (результат, дельта принцесс: отрицательная = штраф, положительная = продажа без бонуса дня).
    """
    prefix = (texts.pick(texts.CAST_PREFIX) + " ") if with_prefix else ""
    event = _roll_neg_event()

    if event == "mermaid":
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

    if random.random() < TRASH_CHANCE:
        trash_key = random.choice(TRASH_TYPES)
        msg = prefix + texts.pick(texts.TRASH[trash_key])
        return CastResult(kind="trash", message=msg), 0

    species = _pick_species()
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
