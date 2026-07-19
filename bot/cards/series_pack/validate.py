from __future__ import annotations

from urllib.parse import urlparse

from .models import (
    CARD_BACK_ID_RE,
    NAME_MAX,
    RARITIES,
    SLUG_RE,
    STORY_MAX,
    BoosterDraft,
    CardDraft,
    DrawDraft,
    PackDraft,
    SeriesDraft,
)


def validate_slug(label: str, value: str) -> list[str]:
    errs: list[str] = []
    if not value or not str(value).strip():
        return [f"{label}: обязательное поле"]
    v = value.strip()
    if v != v.lower():
        errs.append(f"{label}: только нижний регистр")
    if not SLUG_RE.match(v):
        errs.append(
            f"{label}: латиница, начинается с буквы; разрешены a-z 0-9 - _"
        )
    return errs


def validate_series(s: SeriesDraft) -> list[str]:
    errs: list[str] = []
    errs.extend(validate_slug("ID серии", s.series_id))
    name = (s.name or "").strip()
    if not name:
        errs.append("Название серии: обязательное поле")
    elif len(name) > NAME_MAX:
        errs.append(f"Название серии: максимум {NAME_MAX} символов")

    back = (s.card_back_id or "").strip()
    if back and not CARD_BACK_ID_RE.match(back):
        errs.append("ID рубашки: card-back или card-back-… (a-z 0-9 - _)")

    if s.card_back_path is not None:
        if not s.card_back_path.is_file():
            errs.append("Рубашка: файл не найден")
        elif s.card_back_path.suffix.lower() != ".svg":
            errs.append("Рубашка: только .svg")

    try:
        order = int(s.sort_order)
        if order < 0:
            errs.append("Порядок: число ≥ 0")
    except (TypeError, ValueError):
        errs.append("Порядок: целое число")

    return errs


def validate_cards(cards: list[CardDraft]) -> list[str]:
    errs: list[str] = []
    if not cards:
        errs.append("Добавьте хотя бы одну карту")
        return errs

    seen: set[str] = set()
    for i, c in enumerate(cards, start=1):
        prefix = f"Карта #{i}"
        if c.source_path is None and c.paste_image is None:
            errs.append(f"{prefix}: нет изображения")
        errs.extend(validate_slug(f"{prefix} ID", c.card_id))
        cid = (c.card_id or "").strip().lower()
        if cid:
            if cid in seen:
                errs.append(f"{prefix}: дублируется ID «{cid}»")
            seen.add(cid)

        name = (c.name or "").strip()
        if not name:
            errs.append(f"{prefix}: имя персонажа обязательно")
        elif len(name) > NAME_MAX:
            errs.append(f"{prefix}: имя длиннее {NAME_MAX} символов")

        if c.rarity not in RARITIES:
            errs.append(f"{prefix}: неверная редкость")

        story = (c.story or "").strip()
        if not story:
            errs.append(f"{prefix}: описание обязательно")
        elif len(story) > STORY_MAX:
            errs.append(f"{prefix}: описание длиннее {STORY_MAX} символов")

    return errs


def validate_booster(b: BoosterDraft) -> list[str]:
    errs: list[str] = []
    errs.extend(validate_slug("ID бустера", b.booster_id))
    name = (b.name or "").strip()
    if not name:
        errs.append("Название бустера: обязательное поле")
    elif len(name) > NAME_MAX:
        errs.append(f"Название бустера: максимум {NAME_MAX} символов")

    promo = (b.promo_image_url or "").strip()
    if promo:
        p = urlparse(promo)
        if p.scheme not in ("http", "https") or not p.netloc:
            errs.append("Promo URL: нужен http(s)://… или пусто")
    return errs


def validate_draw(d: DrawDraft, card_rarities: set[str]) -> list[str]:
    errs: list[str] = []
    errs.extend(validate_slug("ID тиража", d.draw_id))
    name = (d.name or "").strip()
    if not name:
        errs.append("Название тиража: обязательное поле")

    if int(d.cost_points) <= 0:
        errs.append("Цена: должна быть > 0")
    if int(d.cards_per_open) < 1:
        errs.append("Карт за открытие: минимум 1")
    if int(d.daily_limit) < 0:
        errs.append("Лимит: ≥ 0")

    weights = d.rarity_weights or {}
    total = 0.0
    for k in RARITIES:
        try:
            w = float(weights.get(k, 0) or 0)
        except (TypeError, ValueError):
            errs.append(f"Вес {k}: число")
            continue
        if w < 0:
            errs.append(f"Вес {k}: ≥ 0")
        total += w
    if total <= 0:
        errs.append("Шансы: сумма весов должна быть > 0")

    for k in RARITIES:
        w = float(weights.get(k, 0) or 0)
        if w > 0 and k not in card_rarities:
            errs.append(f"Вес {k}={w}, но в паке нет карт этой редкости")

    return errs


def validate_draft(draft: PackDraft) -> list[str]:
    errs: list[str] = []
    errs.extend(validate_series(draft.series))
    errs.extend(validate_cards(draft.cards))
    errs.extend(validate_booster(draft.booster))
    rarities = {c.rarity for c in draft.cards if c.rarity}
    errs.extend(validate_draw(draft.draw, rarities))
    return errs


def weights_percent_map(weights: dict[str, float]) -> dict[str, str]:
    total = sum(float(weights.get(k, 0) or 0) for k in RARITIES)
    out: dict[str, str] = {}
    for k in RARITIES:
        w = float(weights.get(k, 0) or 0)
        out[k] = f"{(w / total * 100):.1f}" if total > 0 else "0.0"
    return out
