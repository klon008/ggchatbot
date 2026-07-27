"""GoodGame + OBS stream bot."""

from __future__ import annotations

from typing import Any

__all__ = ["StreamBot"]


def __getattr__(name: str) -> Any:
    if name == "StreamBot":
        from .app import StreamBot

        return StreamBot
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
