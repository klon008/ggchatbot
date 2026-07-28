"""Очередь заказов с персистентностью в SQLite."""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from bot.db import Database
from bot.db import queue as queue_db

log = logging.getLogger("song_request.queue")

PROVIDER_YOUTUBE = "youtube"
PROVIDER_YANDEX = "yandex"


@dataclass
class Track:
    video_id: str
    requested_by: str
    url: str
    title: str = ""
    requested_by_name: str = ""
    added_at: float = field(default_factory=time.time)
    paid_cost: int = 0
    provider: str = PROVIDER_YOUTUBE
    album_id: str = ""

    @property
    def track_id(self) -> str:
        """Для ЯМузыки video_id хранит track_id."""
        return self.video_id

    def short_label(self) -> str:
        if self.provider == PROVIDER_YANDEX:
            return f"ym:{self.video_id}"
        return f"yt:{self.video_id}"


def _track_from_dict(item: dict) -> Track:
    data = {k: item[k] for k in Track.__annotations__ if k in item}
    if "provider" not in data or not data.get("provider"):
        data["provider"] = PROVIDER_YOUTUBE
    if "album_id" not in data:
        data["album_id"] = ""
    return Track(**data)


class QueueManager:
    def __init__(self, db: Database, max_size: int = 50) -> None:
        self._db = db
        self.max_size = max_size
        self._queue: list[Track] = []
        self.current: Optional[Track] = None
        self.current_token: Optional[str] = None
        self._next_token_id = 1
        self._loaded = False

    async def load(self) -> None:
        if self._loaded:
            return
        current_dict, _token, counter = await queue_db.load_meta(self._db)
        self._next_token_id = max(counter, 1)
        items = await queue_db.load_items(self._db)
        if current_dict:
            items.insert(0, current_dict)
        self._queue = []
        for item in items:
            try:
                self._queue.append(_track_from_dict(item))
            except (TypeError, KeyError):
                continue
        self.current = None
        self.current_token = None
        self._loaded = True
        log.info("Загружена очередь из %d трек(ов).", len(self._queue))

    async def _save(self) -> None:
        queue_items = [asdict(t) for t in self._queue]
        current = asdict(self.current) if self.current else None
        await queue_db.persist_queue(
            self._db,
            queue_items,
            current,
            self.current_token,
            self._next_token_id,
        )

    def _issue_token(self) -> str:
        token = f"t-{self._next_token_id}"
        self._next_token_id += 1
        return token

    @property
    def is_playing(self) -> bool:
        return self.current is not None

    def __len__(self) -> int:
        return len(self._queue)

    def is_full(self) -> bool:
        return len(self._queue) >= self.max_size

    def count_by_user(self, user_id: str) -> int:
        n = sum(1 for t in self._queue if t.requested_by == user_id)
        if self.current and self.current.requested_by == user_id:
            n += 1
        return n

    async def add(self, track: Track) -> int:
        self._queue.append(track)
        await self._save()
        return len(self._queue) + (1 if self.current else 0)

    async def start_next(self) -> Optional[tuple[Track, str]]:
        if not self._queue:
            self.current = None
            self.current_token = None
            await self._save()
            return None
        self.current = self._queue.pop(0)
        self.current_token = self._issue_token()
        await self._save()
        return self.current, self.current_token

    async def finish_current(self, token: str) -> bool:
        if self.current is None or token != self.current_token:
            log.debug(
                "Отброшено событие с устаревшим token=%s (текущий=%s)",
                token,
                self.current_token,
            )
            return False
        self.current = None
        self.current_token = None
        await self._save()
        return True

    async def force_skip(self) -> None:
        self.current = None
        self.current_token = None
        await self._save()

    def snapshot(self) -> dict:
        return {
            "playing": self.is_playing,
            "current": asdict(self.current) if self.current else None,
            "queueLength": len(self._queue),
        }

    def upcoming(self, limit: int = 5) -> list[Track]:
        return self._queue[:limit]

    def all_tracks(self) -> list[Track]:
        tracks = list(self._queue)
        if self.current is not None:
            tracks.insert(0, self.current)
        return tracks

    async def take_waiting_by_provider(self, provider: str) -> list[Track]:
        """Убрать из ожидания треки выбранного провайдера (current не трогаем)."""
        kept: list[Track] = []
        removed: list[Track] = []
        for t in self._queue:
            if t.provider == provider:
                removed.append(t)
            else:
                kept.append(t)
        self._queue = kept
        await self._save()
        return removed

    def list_waiting(self) -> list[dict]:
        return [
            {
                "index": i,
                "video_id": t.video_id,
                "title": t.title,
                "requested_by": t.requested_by,
                "requested_by_name": t.requested_by_name,
                "url": t.url,
                "added_at": t.added_at,
                "provider": t.provider,
                "album_id": t.album_id,
            }
            for i, t in enumerate(self._queue)
        ]

    async def remove_waiting(self, index: int) -> bool:
        if index < 0 or index >= len(self._queue):
            return False
        del self._queue[index]
        await self._save()
        return True

    async def clear(self) -> None:
        self._queue.clear()
        self.current = None
        self.current_token = None
        self._next_token_id = 1
        await self._save()
