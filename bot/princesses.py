"""Общий справочник принцесс Диснея для princess и races."""

from __future__ import annotations

DISNEY_PRINCESSES: tuple[str, ...] = (
    "Белоснежка",
    "Аврора",
    "Золушка",
    "Мулан",
    "Рапунцель",
    "Тиана",
    "Покахонтас",
    "Ариэль",
    "Жасмин",
    "Эльза",
    "Анна",
    "Моана",
    "Мерида",
    "Бэлль",
    "Ванилопа",
    "Алиса",
    "Эсмеральда",
    "Кида",
    "Мегара",
    "Райя",
    "Джейн Портер",
)

PRINCESS_ICON_SLUG: dict[str, str] = {
    "Белоснежка": "belosnezhka",
    "Аврора": "avrora",
    "Золушка": "zolushka",
    "Мулан": "mulan",
    "Рапунцель": "rapuntsel",
    "Тиана": "tiana",
    "Покахонтас": "pokahontas",
    "Ариэль": "ariel",
    "Жасмин": "zhasmin",
    "Эльза": "elza",
    "Анна": "anna",
    "Моана": "moana",
    "Мерида": "merida",
    "Бэлль": "bell",
    "Ванилопа": "vanilopa",
    "Алиса": "alisa",
    "Эсмеральда": "esmeralda",
    "Кида": "kida",
    "Мегара": "megara",
    "Райя": "raya",
    "Джейн Портер": "jane_porter",
}


def princess_icon_slug(name: str) -> str:
    return PRINCESS_ICON_SLUG.get(name, "unknown")


def princess_icon_path(name: str) -> str:
    slug = princess_icon_slug(name)
    return f"/assets/princesses/{slug}.svg"
