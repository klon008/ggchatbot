"""Общие хелперы для JSON API aiohttp-маршрутов."""
from __future__ import annotations

import json
from typing import Any, Optional

from aiohttp import web


def json_response(data: Any, *, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        charset="utf-8",
        status=status,
    )


def error_response(message: str, *, status: int = 400) -> web.Response:
    return json_response({"error": message}, status=status)


async def read_json(request: web.Request) -> Optional[dict]:
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def parse_balance(raw: Any) -> Optional[int]:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 0:
        return None
    return value


def parse_user_id(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    uid = raw.strip()
    if not uid:
        return None
    return uid


def parse_user_name(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    return raw.strip()
