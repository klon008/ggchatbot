"""Скачивание треков Яндекс Музыки в локальный кэш для OBS <audio>."""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger("song_request.yandex_stream")

_SAFE_TOKEN_RE = re.compile(r"^t-[0-9]+$")


class YandexStreamError(Exception):
    """Ошибка подготовки трека для воспроизведения."""


@dataclass
class CachedTrack:
    play_token: str
    path: Path
    title: str
    duration_sec: float
    content_type: str
    audio_url: str


class YandexStreamService:
    def __init__(self, token: str, cache_dir: Path) -> None:
        self._token = (token or "").strip()
        self._cache_dir = cache_dir
        self._client = None
        self._files: dict[str, Path] = {}

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _ensure_dir(self) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self._token:
            raise YandexStreamError("Яндекс Музыка не настроена (нет YANDEX_MUSIC_TOKEN)")
        from yandex_music import Client

        self._client = Client(self._token).init()
        return self._client

    @staticmethod
    def _track_query(track_id: str, album_id: Optional[str]) -> str:
        if album_id:
            return f"{track_id}:{album_id}"
        return track_id

    @staticmethod
    def _format_title(track) -> str:
        title = (getattr(track, "title", None) or "").strip() or "Без названия"
        artists = getattr(track, "artists", None) or []
        names = []
        for a in artists:
            name = getattr(a, "name", None)
            if name:
                names.append(str(name))
        if names:
            return f"{', '.join(names)} — {title}"
        return title

    @staticmethod
    def _pick_download_info(infos: list):
        if not infos:
            return None
        # Предпочитаем mp3 с максимальным битрейтом.
        mp3 = [i for i in infos if str(getattr(i, "codec", "")).lower() == "mp3"]
        pool = mp3 or list(infos)

        def bitrate(item) -> int:
            try:
                return int(getattr(item, "bitrate_in_kbps", 0) or 0)
            except (TypeError, ValueError):
                return 0

        return max(pool, key=bitrate)

    def _resolve_sync(
        self,
        track_id: str,
        album_id: Optional[str],
        play_token: str,
        known_title: str = "",
    ) -> CachedTrack:
        if not _SAFE_TOKEN_RE.match(play_token):
            raise YandexStreamError("некорректный play token")

        self._ensure_dir()
        existing = self.get_file(play_token)
        if existing and existing[0].is_file() and existing[0].stat().st_size > 0:
            path, content_type = existing
            return CachedTrack(
                play_token=play_token,
                path=path,
                title=known_title or path.stem,
                duration_sec=0.0,
                content_type=content_type,
                audio_url=f"/ym/file/{play_token}",
            )

        client = self._get_client()
        query = self._track_query(track_id, album_id)

        tracks = client.tracks([query])
        if not tracks:
            raise YandexStreamError("трек не найден в Яндекс Музыке")
        track = tracks[0]
        if getattr(track, "error", None):
            raise YandexStreamError(f"трек недоступен ({track.error})")

        title = self._format_title(track)
        duration_ms = getattr(track, "duration_ms", None) or 0
        try:
            duration_sec = float(duration_ms) / 1000.0
        except (TypeError, ValueError):
            duration_sec = 0.0

        track_key = getattr(track, "track_id", None) or query
        infos = client.tracks_download_info(track_key, get_direct_links=False)
        info = self._pick_download_info(infos or [])
        if info is None:
            raise YandexStreamError("нет ссылки для скачивания (нужен Plus?)")

        codec = str(getattr(info, "codec", "mp3") or "mp3").lower()
        ext = "mp3" if codec == "mp3" else ("m4a" if "aac" in codec or "mp4" in codec else codec)
        content_type = "audio/mpeg" if ext == "mp3" else "audio/mp4"
        path = self._cache_dir / f"{play_token}.{ext}"
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

        log.info(
            "Скачивание YM track=%s → %s (codec=%s bitrate=%s)",
            track_key,
            path.name,
            codec,
            getattr(info, "bitrate_in_kbps", "?"),
        )
        info.download(str(path))
        if not path.is_file() or path.stat().st_size <= 0:
            raise YandexStreamError("файл трека пустой после скачивания")

        self._files[play_token] = path
        return CachedTrack(
            play_token=play_token,
            path=path,
            title=title,
            duration_sec=duration_sec,
            content_type=content_type,
            audio_url=f"/ym/file/{play_token}",
        )

    async def resolve_and_cache(
        self,
        track_id: str,
        album_id: Optional[str],
        play_token: str,
        known_title: str = "",
    ) -> CachedTrack:
        return await asyncio.to_thread(
            self._resolve_sync,
            track_id,
            album_id,
            play_token,
            known_title,
        )

    def get_file(self, play_token: str) -> Optional[tuple[Path, str]]:
        if not _SAFE_TOKEN_RE.match(play_token):
            return None
        path = self._files.get(play_token)
        if path is None or not path.is_file():
            # Поиск на диске после рестарта (редко нужно).
            for candidate in self._cache_dir.glob(f"{play_token}.*"):
                if candidate.is_file():
                    ext = candidate.suffix.lower()
                    ctype = "audio/mpeg" if ext == ".mp3" else "audio/mp4"
                    self._files[play_token] = candidate
                    return candidate, ctype
            return None
        ext = path.suffix.lower()
        ctype = "audio/mpeg" if ext == ".mp3" else "audio/mp4"
        return path, ctype

    def cleanup(self, play_token: Optional[str]) -> None:
        if not play_token:
            return
        path = self._files.pop(play_token, None)
        candidates = [path] if path else []
        if self._cache_dir.is_dir():
            candidates.extend(self._cache_dir.glob(f"{play_token}.*"))
        for p in candidates:
            if p is None:
                continue
            try:
                if p.is_file():
                    p.unlink()
            except OSError as exc:
                log.warning("Не удалось удалить кэш YM %s: %s", p, exc)

    def cleanup_all(self) -> None:
        for token in list(self._files.keys()):
            self.cleanup(token)
        if self._cache_dir.is_dir():
            for p in self._cache_dir.glob("t-*"):
                try:
                    if p.is_file():
                        p.unlink()
                except OSError:
                    pass
