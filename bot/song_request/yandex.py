"""Валидация ссылок Яндекс Музыки для !заказ."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

_TRACK_ID_RE = re.compile(r"^[0-9]+$")

_YM_HOSTS = {
    "music.yandex.ru",
    "www.music.yandex.ru",
    "music.yandex.com",
    "www.music.yandex.com",
}

# /album/{album}/track/{track}
_ALBUM_TRACK_RE = re.compile(
    r"/album/([0-9]+)/track/([0-9]+)",
    re.IGNORECASE,
)
# /track/{track}
_TRACK_ONLY_RE = re.compile(r"/track/([0-9]+)(?:/|$)", re.IGNORECASE)
# #track/{track}/{album} или #track/{track}/
_IFRAME_HASH_RE = re.compile(
    r"#track/([0-9]+)(?:/([0-9]+))?",
    re.IGNORECASE,
)


@dataclass
class ValidationResult:
    ok: bool
    track_id: Optional[str] = None
    album_id: Optional[str] = None
    reason: Optional[str] = None


def _extract(raw: str) -> tuple[Optional[str], Optional[str]]:
    text = html.unescape(raw.strip())
    token = next(
        (
            w
            for w in text.split()
            if "music.yandex." in w.lower() or "yandex.ru/iframe" in w.lower()
        ),
        None,
    )
    if token is None:
        return None, None
    if not re.match(r"^https?://", token, re.IGNORECASE):
        token = "https://" + token

    try:
        parsed = urlparse(token)
    except ValueError:
        return None, None

    host = (parsed.hostname or "").lower()
    if host not in _YM_HOSTS:
        return None, None

    path = parsed.path or ""
    frag = parsed.fragment or ""

    m = _ALBUM_TRACK_RE.search(path)
    if m:
        return m.group(2), m.group(1)

    m = _IFRAME_HASH_RE.search(frag) or _IFRAME_HASH_RE.search(token)
    if m:
        track_id = m.group(1)
        album_id = m.group(2) or None
        return track_id, album_id

    m = _TRACK_ONLY_RE.search(path)
    if m:
        return m.group(1), None

    return None, None


def validate_request(raw: str) -> ValidationResult:
    if not raw or not raw.strip():
        return ValidationResult(False, reason="укажи ссылку на Яндекс Музыку после !заказ")

    track_id, album_id = _extract(raw)
    if track_id is None or not _TRACK_ID_RE.match(track_id):
        return ValidationResult(False, reason="не нашёл валидную ссылку на трек Яндекс Музыки")
    if album_id is not None and not _TRACK_ID_RE.match(album_id):
        album_id = None

    return ValidationResult(True, track_id=track_id, album_id=album_id)


def canonical_url(track_id: str, album_id: Optional[str] = None) -> str:
    if album_id:
        return f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    return f"https://music.yandex.ru/track/{track_id}"


def embed_url(track_id: str, album_id: Optional[str] = None) -> str:
    if album_id:
        return f"https://music.yandex.ru/iframe/#track/{track_id}/{album_id}"
    return f"https://music.yandex.ru/iframe/#track/{track_id}/"
