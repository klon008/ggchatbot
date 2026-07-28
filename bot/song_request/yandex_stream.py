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
_AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".mp4", ".flac", ".ogg", ".opus"}
_COVER_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


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
    cover_url: str = ""


class YandexStreamService:
    def __init__(self, token: str, cache_dir: Path) -> None:
        self._token = (token or "").strip()
        self._cache_dir = cache_dir
        self._client = None
        self._files: dict[str, Path] = {}
        self._covers: dict[str, Path] = {}

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
        mp3 = [i for i in infos if str(getattr(i, "codec", "")).lower() == "mp3"]
        pool = mp3 or list(infos)

        def bitrate(item) -> int:
            try:
                return int(getattr(item, "bitrate_in_kbps", 0) or 0)
            except (TypeError, ValueError):
                return 0

        return max(pool, key=bitrate)

    def _find_audio_on_disk(self, play_token: str) -> Optional[Path]:
        if not self._cache_dir.is_dir():
            return None
        for candidate in self._cache_dir.glob(f"{play_token}.*"):
            if candidate.is_file() and candidate.suffix.lower() in _AUDIO_EXTS:
                return candidate
        return None

    def _find_cover_on_disk(self, play_token: str) -> Optional[Path]:
        if not self._cache_dir.is_dir():
            return None
        for candidate in self._cache_dir.glob(f"{play_token}.*"):
            if candidate.is_file() and candidate.suffix.lower() in _COVER_EXTS:
                return candidate
        return None

    def _download_cover(self, track, play_token: str) -> Optional[Path]:
        cover_path = self._cache_dir / f"{play_token}.jpg"
        try:
            if hasattr(track, "download_cover"):
                track.download_cover(str(cover_path), size="400x400")
            elif hasattr(track, "downloadCover"):
                track.downloadCover(str(cover_path), size="400x400")
            else:
                return None
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось скачать обложку YM: %s", exc)
            if cover_path.exists():
                try:
                    cover_path.unlink()
                except OSError:
                    pass
            return None
        if cover_path.is_file() and cover_path.stat().st_size > 0:
            self._covers[play_token] = cover_path
            return cover_path
        return None

    def _cover_url_for(self, play_token: str) -> str:
        cover = self._covers.get(play_token) or self._find_cover_on_disk(play_token)
        if cover and cover.is_file():
            self._covers[play_token] = cover
            return f"/ym/cover/{play_token}"
        return ""

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
                cover_url=self._cover_url_for(play_token),
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

        self._download_cover(track, play_token)

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
            cover_url=self._cover_url_for(play_token),
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
            path = self._find_audio_on_disk(play_token)
            if path is None:
                return None
            self._files[play_token] = path
        ext = path.suffix.lower()
        ctype = "audio/mpeg" if ext == ".mp3" else "audio/mp4"
        return path, ctype

    def get_cover(self, play_token: str) -> Optional[tuple[Path, str]]:
        if not _SAFE_TOKEN_RE.match(play_token):
            return None
        path = self._covers.get(play_token)
        if path is None or not path.is_file():
            path = self._find_cover_on_disk(play_token)
            if path is None:
                return None
            self._covers[play_token] = path
        ext = path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            ctype = "image/jpeg"
        elif ext == ".png":
            ctype = "image/png"
        elif ext == ".webp":
            ctype = "image/webp"
        else:
            ctype = "image/jpeg"
        return path, ctype

    def cleanup(self, play_token: Optional[str]) -> None:
        if not play_token:
            return
        self._files.pop(play_token, None)
        self._covers.pop(play_token, None)
        if self._cache_dir.is_dir():
            for p in self._cache_dir.glob(f"{play_token}.*"):
                try:
                    if p.is_file():
                        p.unlink()
                except OSError as exc:
                    log.warning("Не удалось удалить кэш YM %s: %s", p, exc)

    def cleanup_all(self) -> None:
        tokens = set(self._files.keys()) | set(self._covers.keys())
        for token in list(tokens):
            self.cleanup(token)
        if self._cache_dir.is_dir():
            for p in self._cache_dir.glob("t-*"):
                try:
                    if p.is_file():
                        p.unlink()
                except OSError:
                    pass
