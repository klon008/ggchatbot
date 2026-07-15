"""Единый реестр публичных команд бота."""
from __future__ import annotations

HELP_COMMAND = "!команды"

PRINCESS_COMMANDS = (
    "!баллы",
    "!дейлик",
    "!дайс",
    "!кража",
    "!карман",
    "!срок",
    "!дисней",
    "!нейро",
    "!звук",
    "!коллекция",
)

SONG_REQUEST_COMMANDS = (
    "!заказ",
    "!очередь",
    "!играет",
)

ROULETTE_COMMANDS = (
    "!рулетка",
)

RACES_COMMANDS = (
    "!забег",
)

POLLS_COMMANDS = (
    "!опрос",
)

CARDS_COMMANDS = (
    "!бустер",
    "!альбом",
)

PUBLIC_COMMANDS = (
    PRINCESS_COMMANDS
    + CARDS_COMMANDS
    + ROULETTE_COMMANDS
    + RACES_COMMANDS
    + POLLS_COMMANDS
    + SONG_REQUEST_COMMANDS
)


def format_help() -> str:
    return "Команды: " + " ".join(PUBLIC_COMMANDS)
