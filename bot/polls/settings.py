"""Настройки модуля опросов (predictions)."""

from __future__ import annotations

# Длительность сбора ставок (секунды)
POLL_MIN_COLLECT_SEC = 60
POLL_MAX_COLLECT_SEC = 600
POLL_DEFAULT_COLLECT_SEC = 300

POLL_MIN_OPTIONS = 2
POLL_MAX_OPTIONS = 8

POLL_MIN_STAKE = 10

# Сколько держать RESOLVED на оверлее перед возвратом в IDLE
POLL_RESOLVED_DISPLAY_SEC = 15

POLL_CMD = "!опрос"
