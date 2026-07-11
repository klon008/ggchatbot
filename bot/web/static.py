"""Раздача статики из каталога obs/."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

OBS_DIR = Path(__file__).resolve().parent.parent.parent / "obs"


async def serve_obs_file(name: str, content_type: str) -> web.StreamResponse:
    path = OBS_DIR / name
    if not path.exists():
        return web.Response(status=404, text=f"{name} not found")
    return web.Response(
        body=path.read_bytes(),
        content_type=content_type.split(";")[0],
        charset="utf-8",
    )
