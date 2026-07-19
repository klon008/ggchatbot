"""Проверка дублей id/названий в БД для wizard series-pack."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from bot.db import cards as cards_db

if TYPE_CHECKING:
    from bot.db import Database


def _norm_name(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


async def check_step_conflicts(
    db: "Database",
    *,
    step: int,
    payload: dict[str, Any],
) -> list[str]:
    """step: 0 series, 1 cards, 2 booster, 3 draw. Returns Russian error messages."""
    errs: list[str] = []

    if step == 0:
        sid = str(payload.get("series_id") or "").strip().lower()
        sname = str(payload.get("name") or "").strip()
        if sid and await cards_db.series_exists(db, sid):
            errs.append(f"ID серии «{sid}» уже есть в БД")
        if sname:
            for s in await cards_db.list_series(db):
                if _norm_name(s.get("name") or "") == _norm_name(sname):
                    errs.append(
                        f"Название серии «{sname}» уже используется "
                        f"(id={s.get('id')})"
                    )
                    break

    elif step == 1:
        cards = payload.get("cards") or []
        if not isinstance(cards, list):
            return ["Карты: некорректный формат"]
        catalog = await cards_db.list_catalog_cards(db)
        by_id = {str(c["id"]).lower(): c for c in catalog}
        by_name = {_norm_name(c["name"]): c for c in catalog if c.get("name")}
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        for i, c in enumerate(cards, start=1):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("card_id") or c.get("id") or "").strip().lower()
            cname = str(c.get("name") or "").strip()
            if cid:
                if cid in seen_ids:
                    errs.append(f"Карта #{i}: дубль ID «{cid}» в пакете")
                seen_ids.add(cid)
                if cid in by_id:
                    errs.append(f"ID карты «{cid}» уже есть в БД")
            if cname:
                nn = _norm_name(cname)
                if nn in seen_names:
                    errs.append(f"Карта #{i}: дубль имени «{cname}» в пакете")
                seen_names.add(nn)
                if nn in by_name:
                    other = by_name[nn]
                    errs.append(
                        f"Имя карты «{cname}» уже есть в БД "
                        f"(id={other.get('id')})"
                    )

    elif step == 2:
        bid = str(payload.get("booster_id") or "").strip().lower()
        bname = str(payload.get("name") or "").strip()
        if bid and await cards_db.booster_exists(db, bid):
            errs.append(f"ID бустера «{bid}» уже есть в БД")
        if bname:
            for b in await cards_db.list_boosters(db):
                if _norm_name(b.get("name") or "") == _norm_name(bname):
                    errs.append(
                        f"Название бустера «{bname}» уже используется "
                        f"(id={b.get('id')})"
                    )
                    break

    elif step == 3:
        did = str(payload.get("draw_id") or "").strip().lower()
        dname = str(payload.get("name") or "").strip()
        if did and await cards_db.draw_exists(db, did):
            errs.append(f"ID тиража «{did}» уже есть в БД")
        if dname:
            for d in await cards_db.list_draws(db):
                if _norm_name(d.get("name") or "") == _norm_name(dname):
                    errs.append(
                        f"Название тиража «{dname}» уже используется "
                        f"(id={d.get('id')})"
                    )
                    break

    return errs
