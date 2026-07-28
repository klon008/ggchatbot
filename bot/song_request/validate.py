"""Роутер валидации заказа: YouTube или Яндекс Музыка по ссылке."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from . import yandex as ym
from . import youtube as yt

Provider = Literal["youtube", "yandex"]


@dataclass
class OrderValidation:
    ok: bool
    provider: Optional[Provider] = None
    media_id: Optional[str] = None
    album_id: str = ""
    url: str = ""
    reason: Optional[str] = None


def _looks_like_yandex(raw: str) -> bool:
    low = raw.lower()
    return "music.yandex." in low or "yandex.ru/iframe" in low


def _looks_like_youtube(raw: str) -> bool:
    low = raw.lower()
    return "youtu" in low


def validate_order(raw: str) -> OrderValidation:
    if not raw or not raw.strip():
        return OrderValidation(
            False,
            reason="укажи ссылку на YouTube или Яндекс Музыку после !заказ",
        )

    prefer_ym = _looks_like_yandex(raw)
    prefer_yt = _looks_like_youtube(raw)

    if prefer_ym and not prefer_yt:
        result = ym.validate_request(raw)
        if not result.ok:
            return OrderValidation(False, reason=result.reason)
        album = result.album_id or ""
        return OrderValidation(
            True,
            provider="yandex",
            media_id=result.track_id,
            album_id=album,
            url=ym.canonical_url(result.track_id or "", result.album_id),
        )

    if prefer_yt and not prefer_ym:
        result = yt.validate_request(raw)
        if not result.ok:
            return OrderValidation(False, reason=result.reason)
        return OrderValidation(
            True,
            provider="youtube",
            media_id=result.video_id,
            url=yt.canonical_url(result.video_id or ""),
        )

    # Неоднозначно или без явных маркеров — пробуем оба (ЯМузыка первой).
    ym_result = ym.validate_request(raw)
    if ym_result.ok:
        album = ym_result.album_id or ""
        return OrderValidation(
            True,
            provider="yandex",
            media_id=ym_result.track_id,
            album_id=album,
            url=ym.canonical_url(ym_result.track_id or "", ym_result.album_id),
        )

    yt_result = yt.validate_request(raw)
    if yt_result.ok:
        return OrderValidation(
            True,
            provider="youtube",
            media_id=yt_result.video_id,
            url=yt.canonical_url(yt_result.video_id or ""),
        )

    return OrderValidation(
        False,
        reason="не нашёл валидную ссылку на YouTube или Яндекс Музыку",
    )
