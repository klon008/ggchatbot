"""Валидация YouTube-ссылок.

MVP: извлекаем 11-символьный videoId из разных форматов ссылок без Data API.
Проверки длительности / live / embeddable / 18+ выполняются на стороне плеера
(IFrame API ``getDuration``/``onError``), см. obs/player.js.

TODO: класс-наследник с YouTube Data API для pre-check длительности, 18+ и
стоп-слов до постановки в очередь (нужен YOUTUBE_API_KEY).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, urlparse

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Прямой videoId в разных хостах/путях.
_PATH_PATTERNS = [
    re.compile(r"(?:youtu\.be)/([A-Za-z0-9_-]{11})"),
    re.compile(r"/shorts/([A-Za-z0-9_-]{11})"),
    re.compile(r"/embed/([A-Za-z0-9_-]{11})"),
    re.compile(r"/live/([A-Za-z0-9_-]{11})"),
    re.compile(r"/v/([A-Za-z0-9_-]{11})"),
]

_YT_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}


@dataclass
class ValidationResult:
    ok: bool
    video_id: Optional[str] = None
    reason: Optional[str] = None  # текст для ответа в чат при ошибке


def _extract_video_id(raw: str) -> Optional[str]:
    text = html.unescape(raw.strip())
    # Достаём первое похожее на URL слово.
    token = next((w for w in text.split() if "youtu" in w.lower()), None)
    if token is None:
        return None
    if not re.match(r"^https?://", token, re.IGNORECASE):
        token = "https://" + token

    try:
        parsed = urlparse(token)
    except ValueError:
        return None

    host = (parsed.hostname or "").lower()
    if host not in _YT_HOSTS:
        return None

    # watch?v=ID
    if parsed.path in ("/watch", "/watch/"):
        vid = parse_qs(parsed.query).get("v", [None])[0]
        if vid and _VIDEO_ID_RE.match(vid):
            return vid

    # youtu.be/ID, /shorts/ID, /embed/ID, /live/ID, /v/ID
    for pat in _PATH_PATTERNS:
        m = pat.search(token)
        if m:
            return m.group(1)

    return None


def validate_request(raw: str) -> ValidationResult:
    """Синхронная валидация запроса из ``!sr <текст>``."""
    if not raw or not raw.strip():
        return ValidationResult(False, reason="укажи ссылку на YouTube после !sr")

    video_id = _extract_video_id(raw)
    if video_id is None:
        return ValidationResult(False, reason="не нашёл валидную ссылку на YouTube-видео")

    return ValidationResult(True, video_id=video_id)


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
