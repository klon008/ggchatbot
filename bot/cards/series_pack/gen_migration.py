from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def next_migration_version(migrations_dir: Path) -> int:
    max_v = 0
    for p in migrations_dir.glob("m*.py"):
        m = re.match(r"m(\d+)_", p.name)
        if m:
            max_v = max(max_v, int(m.group(1)))
    return max_v + 1


def _py_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def generate_migration_source(
    version: int,
    series: dict[str, Any],
    booster: dict[str, Any],
    draw: dict[str, Any],
    cards: list[dict[str, Any]],
) -> str:
    sid = series["id"]
    sname = series["name"]
    back = series["card_back_id"]
    sort_order = int(series.get("sort_order", 1))
    bid = booster["id"]
    bname = booster["name"]
    promo = booster.get("promo_image_url")
    promo_lit = "None" if not promo else _py_str(str(promo))
    did = draw["id"]
    dname = draw["name"]
    cost = int(draw["cost_points"])
    n_cards = int(draw["cards_per_open"])
    limit = int(draw.get("daily_limit") or 0)
    status = str(draw.get("status") or "queued")
    weights = draw.get("rarity_weights") or {}

    catalog_lines = []
    for c in cards:
        catalog_lines.append(
            f"    ({_py_str(c['id'])}, {_py_str(c['name'])}, {_py_str(c['rarity'])}, {int(c.get('sort_order', 0))}),"
        )
    catalog_body = "\n".join(catalog_lines)

    weights_lit = ",\n".join(
        f"    {_py_str(k)}: {float(weights.get(k, 0) or 0)}"
        for k in (
            "common",
            "uncommon",
            "rare",
            "epic",
            "legendary",
            "mythic",
            "secretRare",
        )
    )

    return f'''"""Migration {version:03d}: серия «{sname}» + карты + бустер/тираж (series-pack-web)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

from .m009_elsa_mythic import portrait_path

VERSION = {version}
DESCRIPTION = "Серия {sid}: {sname}, рубашка, карты, бустер+тираж"

_SERIES_ID = {_py_str(sid)}
_SERIES_NAME = {_py_str(sname)}
_CARD_BACK_ID = {_py_str(back)}
_SERIES_SORT = {sort_order}
_BOOSTER_ID = {_py_str(bid)}
_BOOSTER_NAME = {_py_str(bname)}
_PROMO_URL = {promo_lit}
_DRAW_ID = {_py_str(did)}
_DRAW_NAME = {_py_str(dname)}
_DRAW_STATUS = {_py_str(status)}
_COST = {cost}
_CARDS_PER_OPEN = {n_cards}
_DAILY_LIMIT = {limit}

_CATALOG: list[tuple[str, str, str, int]] = [
{catalog_body}
]

_WEIGHTS = {{
{weights_lit}
}}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


async def upgrade(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO card_series (id, name, sort_order, card_back_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            sort_order = excluded.sort_order,
            card_back_id = excluded.card_back_id
        """,
        (_SERIES_ID, _SERIES_NAME, _SERIES_SORT, _CARD_BACK_ID),
    )

    for card_id, name, rarity, sort_order in _CATALOG:
        await conn.execute(
            """
            INSERT INTO cards (id, series_id, name, rarity, sort_order, image_url)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                series_id = excluded.series_id,
                name = excluded.name,
                rarity = excluded.rarity,
                sort_order = excluded.sort_order,
                image_url = excluded.image_url
            """,
            (
                card_id,
                _SERIES_ID,
                name,
                rarity,
                sort_order,
                portrait_path(card_id),
            ),
        )

    now = _utcnow_iso()
    await conn.execute(
        """
        INSERT INTO boosters (id, name, promo_image_url, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            promo_image_url = excluded.promo_image_url
        """,
        (_BOOSTER_ID, _BOOSTER_NAME, _PROMO_URL, now),
    )

    for card_id, _, _, _ in _CATALOG:
        await conn.execute(
            """
            INSERT OR IGNORE INTO booster_pool (booster_id, card_id)
            VALUES (?, ?)
            """,
            (_BOOSTER_ID, card_id),
        )

    await conn.execute(
        """
        INSERT INTO draws (
            id, booster_id, name, cost_points, cards_per_open,
            rarity_weights, status, daily_limit, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            booster_id = excluded.booster_id,
            name = excluded.name,
            cost_points = excluded.cost_points,
            cards_per_open = excluded.cards_per_open,
            rarity_weights = excluded.rarity_weights,
            daily_limit = excluded.daily_limit
        """,
        (
            _DRAW_ID,
            _BOOSTER_ID,
            _DRAW_NAME,
            _COST,
            _CARDS_PER_OPEN,
            json.dumps(_WEIGHTS, ensure_ascii=False),
            _DRAW_STATUS,
            _DAILY_LIMIT,
            now,
        ),
    )
'''


def register_migration(init_path: Path, module_name: str) -> None:
    text = init_path.read_text(encoding="utf-8")
    if module_name in text:
        return

    import_block_pat = re.compile(
        r"(from \. import \()(.*?)(\n\))",
        re.DOTALL,
    )

    def add_import(m: re.Match[str]) -> str:
        body = m.group(2).rstrip()
        if not body.endswith(","):
            body += ","
        body += f"\n    {module_name},"
        return f"{m.group(1)}{body}{m.group(3)}"

    text2, n = import_block_pat.subn(add_import, text, count=1)
    if n != 1:
        raise RuntimeError("Не удалось вставить import в migrations/__init__.py")

    list_pat = re.compile(
        r"(MIGRATIONS: list\[Migration\] = \[)(.*?)(\n\])",
        re.DOTALL,
    )

    def add_list(m: re.Match[str]) -> str:
        body = m.group(2).rstrip()
        if not body.endswith(","):
            body += ","
        body += f"\n    {module_name},"
        return f"{m.group(1)}{body}{m.group(3)}"

    text3, n2 = list_pat.subn(add_list, text2, count=1)
    if n2 != 1:
        raise RuntimeError("Не удалось вставить модуль в MIGRATIONS")

    init_path.write_text(text3, encoding="utf-8", newline="\n")
