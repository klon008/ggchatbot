"""Очередь заказов с атомарной персистентностью на диск.

Python — единственный источник правды о состоянии воспроизведения.
Каждый трек при постановке в play получает уникальный ``token`` для защиты
от гонок (двойной ``ended``/``skip`` и запоздавшие события плеера).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from itertools import count
from pathlib import Path
from typing import Optional

log = logging.getLogger("queue")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
QUEUE_FILE = DATA_DIR / "queue.json"


@dataclass
class Track:
    video_id: str
    requested_by: str
    url: str
    title: str = ""
    requested_by_name: str = ""
    added_at: float = field(default_factory=time.time)


class QueueManager:
    def __init__(self, max_size: int = 50) -> None:
        self.max_size = max_size
        self._queue: list[Track] = []
        self.current: Optional[Track] = None
        self.current_token: Optional[str] = None
        self._token_counter = count(1)
        self._load()

    # --- персистентность -------------------------------------------------
    def _load(self) -> None:
        if not QUEUE_FILE.exists():
            return
        try:
            data = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Не удалось прочитать %s: %s. Начинаем с пустой очереди.", QUEUE_FILE, exc)
            return

        items = data.get("queue", [])
        # Трек, который «играл» на момент падения, возвращаем в голову очереди.
        current = data.get("current")
        if current:
            items.insert(0, current)
        for item in items:
            try:
                self._queue.append(Track(**{k: item[k] for k in Track.__annotations__ if k in item}))
            except (TypeError, KeyError):
                continue
        log.info("Загружена очередь из %d трек(ов).", len(self._queue))

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "current": asdict(self.current) if self.current else None,
            "queue": [asdict(t) for t in self._queue],
        }
        tmp = QUEUE_FILE.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, QUEUE_FILE)  # атомарная замена
        except OSError as exc:
            log.error("Не удалось сохранить очередь: %s", exc)

    # --- операции --------------------------------------------------------
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

    def add(self, track: Track) -> int:
        """Добавить в конец очереди. Возвращает позицию (1-based) в общей очереди."""
        self._queue.append(track)
        self._save()
        return len(self._queue) + (1 if self.current else 0)

    def start_next(self) -> Optional[tuple[Track, str]]:
        """Взять голову очереди в ``current`` и выдать новый token.

        Возвращает ``(track, token)`` либо ``None``, если очередь пуста.
        """
        if not self._queue:
            self.current = None
            self.current_token = None
            self._save()
            return None
        self.current = self._queue.pop(0)
        self.current_token = f"t-{next(self._token_counter)}"
        self._save()
        return self.current, self.current_token

    def finish_current(self, token: str) -> bool:
        """Завершить текущий трек, если ``token`` актуален.

        Возвращает True, если событие принято (токен совпал).
        Устаревшие события (double ended / гонка со skip) отбрасываются.
        """
        if self.current is None or token != self.current_token:
            log.debug("Отброшено событие с устаревшим token=%s (текущий=%s)", token, self.current_token)
            return False
        self.current = None
        self.current_token = None
        self._save()
        return True

    def force_skip(self) -> None:
        """Принудительно сбросить текущий трек (watchdog / !skip без токена)."""
        self.current = None
        self.current_token = None
        self._save()

    def snapshot(self) -> dict:
        return {
            "playing": self.is_playing,
            "current": asdict(self.current) if self.current else None,
            "queueLength": len(self._queue),
        }

    def upcoming(self, limit: int = 5) -> list[Track]:
        return self._queue[:limit]

    def clear(self) -> None:
        self._queue.clear()
        self.current = None
        self.current_token = None
        self._save()
