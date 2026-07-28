"""Получить OAuth-токен Яндекс Музыки (Device Flow) для .env.

Запуск:
  python tools/yandex_music_token.py

Скопируйте access_token в .env:
  YANDEX_MUSIC_TOKEN=...
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from yandex_music import Client
    except ImportError:
        print("Установите зависимость: pip install yandex-music", file=sys.stderr)
        return 1

    def on_code(code) -> None:
        url = getattr(code, "verification_url", None) or "https://ya.ru"
        user_code = getattr(code, "user_code", "?")
        print()
        print(f"Откройте: {url}")
        print(f"Введите код: {user_code}")
        print("Подтвердите вход в аккаунт с Яндекс Плюс…")
        print()

    print("Запрос Device Flow (Яндекс Музыка)…")
    client = Client()
    try:
        token = client.device_auth(on_code=on_code)
    except Exception as exc:  # noqa: BLE001
        print(f"Ошибка авторизации: {exc}", file=sys.stderr)
        print(
            "Если Device Flow недоступен — см. https://ym.marshal.dev/token",
            file=sys.stderr,
        )
        return 1

    access = getattr(token, "access_token", None) or str(token)
    refresh = getattr(token, "refresh_token", None)
    expires = getattr(token, "expires_in", None)

    print()
    print("Готово. Добавьте в .env:")
    print(f"YANDEX_MUSIC_TOKEN={access}")
    if refresh:
        print(f"# refresh_token={refresh}")
    if expires:
        print(f"# expires_in={expires}")
    print()
    print("Перезапустите бота после сохранения .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
