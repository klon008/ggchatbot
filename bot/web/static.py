"""Раздача статики из каталога obs/."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web

OBS_DIR = Path(__file__).resolve().parent.parent.parent / "obs"
OBS_ASSETS_DIR = OBS_DIR / "assets"

_CONTENT_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".css": "text/css",
    ".js": "application/javascript",
    ".html": "text/html",
    ".htm": "text/html",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


async def serve_obs_file(name: str, content_type: str) -> web.StreamResponse:
    path = OBS_DIR / name
    if not path.exists():
        return web.Response(status=404, text=f"{name} not found")
    return web.Response(
        body=path.read_bytes(),
        content_type=content_type.split(";")[0],
        charset="utf-8",
    )


async def serve_obs_asset(relative_path: str) -> web.StreamResponse:
    """Раздача файла из obs/assets/ по относительному пути (без ..)."""
    return await _serve_under(OBS_ASSETS_DIR, relative_path)


async def serve_obs_card_template(relative_path: str) -> web.StreamResponse:
    """Раздача файлов из obs/card-templates/ (рамки карт для OBS)."""
    return await _serve_under(OBS_DIR / "card-templates", relative_path)


async def serve_obs_test(relative_path: str) -> web.StreamResponse:
    """Раздача файлов из obs/test/ (эксперименты / превью)."""
    return await _serve_under(OBS_DIR / "test", relative_path)


async def _serve_under(base_dir: Path, relative_path: str) -> web.StreamResponse:
    base = base_dir.resolve()
    path = (base_dir / relative_path).resolve()
    if not str(path).startswith(str(base)) or not path.is_file():
        return web.Response(status=404, text="asset not found")
    suffix = path.suffix.lower()
    content_type = _CONTENT_TYPES.get(suffix, "application/octet-stream")
    kwargs: dict = {"body": path.read_bytes(), "content_type": content_type}
    if content_type.startswith("text/") or content_type in (
        "application/javascript",
        "image/svg+xml",
    ):
        kwargs["charset"] = "utf-8"
    return web.Response(**kwargs)
