"""Runtime-настройки рыбалки: defaults из settings.py + override из fishing_meta."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from bot.db import fishing as fishing_db
from bot.db.connection import Database

from . import settings as S

INT_KEYS = (
    "energy_max",
    "energy_regen_interval_sec",
    "cast_energy_cost",
    "worms_energy_cost",
    "worms_gain",
    "maggot_cost",
    "maggot_gain",
    "rod_cost",
    "cast_cooldown_sec",
    "bite_boost_casts",
    "bite_boost_miss_trash_div",
)

FLOAT_KEYS = (
    "worms_dig_shield_chance",
    "worms_dig_bite_chance",
    "worms_dig_safe_chance",
    "miss_chance",
    "trash_chance",
)

ALL_KEYS = INT_KEYS + FLOAT_KEYS


@dataclass
class FishingRuntimeSettings:
    energy_max: int
    energy_regen_interval_sec: int
    cast_energy_cost: int
    worms_energy_cost: int
    worms_gain: int
    maggot_cost: int
    maggot_gain: int
    rod_cost: int
    cast_cooldown_sec: int
    bite_boost_casts: int
    bite_boost_miss_trash_div: int
    worms_dig_shield_chance: float
    worms_dig_bite_chance: float
    worms_dig_safe_chance: float
    miss_chance: float
    trash_chance: float

    @classmethod
    def defaults(cls) -> "FishingRuntimeSettings":
        return cls(
            energy_max=int(S.ENERGY_MAX),
            energy_regen_interval_sec=int(S.ENERGY_REGEN_INTERVAL_SEC),
            cast_energy_cost=int(S.CAST_ENERGY_COST),
            worms_energy_cost=int(S.WORMS_ENERGY_COST),
            worms_gain=int(S.WORMS_GAIN),
            maggot_cost=int(S.MAGGOT_COST),
            maggot_gain=int(S.MAGGOT_GAIN),
            rod_cost=int(S.ROD_COST),
            cast_cooldown_sec=int(S.CAST_COOLDOWN_SEC),
            bite_boost_casts=int(S.BITE_BOOST_CASTS),
            bite_boost_miss_trash_div=int(S.BITE_BOOST_MISS_TRASH_DIV),
            worms_dig_shield_chance=float(S.WORMS_DIG_SHIELD_CHANCE),
            worms_dig_bite_chance=float(S.WORMS_DIG_BITE_CHANCE),
            worms_dig_safe_chance=float(S.WORMS_DIG_SAFE_CHANCE),
            miss_chance=float(S.MISS_CHANCE),
            trash_chance=float(S.TRASH_CHANCE),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_override(cls, override: Optional[dict[str, Any]]) -> "FishingRuntimeSettings":
        base = cls.defaults()
        if not override:
            return base
        data = base.to_dict()
        for key in ALL_KEYS:
            if key not in override:
                continue
            data[key] = override[key]
        return validate(data)


def validate(raw: dict[str, Any]) -> FishingRuntimeSettings:
    """Проверка и нормализация. ValueError(key) при ошибке."""
    if not isinstance(raw, dict):
        raise ValueError("payload")

    out: dict[str, Any] = FishingRuntimeSettings.defaults().to_dict()

    for key in INT_KEYS:
        if key not in raw:
            continue
        val = raw[key]
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(key)
        out[key] = val

    for key in FLOAT_KEYS:
        if key not in raw:
            continue
        val = raw[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ValueError(key)
        out[key] = float(val)

    if out["energy_max"] < 1:
        raise ValueError("energy_max")
    if out["energy_regen_interval_sec"] < 1:
        raise ValueError("energy_regen_interval_sec")
    if out["cast_energy_cost"] < 0:
        raise ValueError("cast_energy_cost")
    if out["worms_energy_cost"] < 0:
        raise ValueError("worms_energy_cost")
    if out["worms_gain"] < 0:
        raise ValueError("worms_gain")
    if out["maggot_cost"] < 0:
        raise ValueError("maggot_cost")
    if out["maggot_gain"] < 0:
        raise ValueError("maggot_gain")
    if out["rod_cost"] < 0:
        raise ValueError("rod_cost")
    if out["cast_cooldown_sec"] < 0:
        raise ValueError("cast_cooldown_sec")
    if out["bite_boost_casts"] < 0:
        raise ValueError("bite_boost_casts")
    if out["bite_boost_miss_trash_div"] < 1:
        raise ValueError("bite_boost_miss_trash_div")

    for key in FLOAT_KEYS:
        chance = float(out[key])
        if chance < 0.0 or chance > 1.0:
            raise ValueError(key)
        out[key] = chance

    dig_sum = (
        out["worms_dig_shield_chance"]
        + out["worms_dig_bite_chance"]
        + out["worms_dig_safe_chance"]
    )
    if dig_sum > 1.0 + 1e-9:
        raise ValueError("dig_chances_sum")

    if out["miss_chance"] + out["trash_chance"] > 1.0 + 1e-9:
        raise ValueError("miss_trash_sum")

    return FishingRuntimeSettings(**out)


async def load_runtime(db: Database) -> FishingRuntimeSettings:
    override = await fishing_db.get_settings_override(db)
    return FishingRuntimeSettings.from_override(override)
