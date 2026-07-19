"""Арты плашки недельного рекорда (OBS). Едут с обновлением — не в settings.py.

Файлы: obs/assets/fishing/{slug}.png
"""

from __future__ import annotations

# Вид рыбы → имя файла без расширения
FISH_RECORD_ASSETS: dict[str, str] = {
    "Карась": "karas",
    "Плотва": "plotva",
    "Окунь": "okun",
    "Лещ": "lesh",
    "Щука": "shuka",
    "Сом": "som",
    "Осётр": "osetr",
}
