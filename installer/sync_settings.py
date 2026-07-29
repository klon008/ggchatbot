#!/usr/bin/env python3
"""Дописать в settings.py недостающие константы из settings.example.py.

Существующие значения не меняет. Используется при update.cmd.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Модули с парой settings.py / settings.example.py (как в update.ps1).
DEFAULT_DIRS = (
    "bot/princess",
    "bot/song_request",
    "bot/roulette",
    "bot/minigames",
    "bot/races",
    "bot/fishing",
)

MARKER = "# --- auto-added from settings.example.py (sync_settings) ---"


def _assignment_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                names.append(target.id)
    elif isinstance(node, ast.AnnAssign):
        target = node.target
        if (
            isinstance(target, ast.Name)
            and not target.id.startswith("_")
            and node.value is not None
        ):
            names.append(target.id)
    return names


def collect_top_level_assigns(tree: ast.AST) -> dict[str, ast.AST]:
    """Имя -> первый top-level Assign/AnnAssign в порядке появления."""
    found: dict[str, ast.AST] = {}
    for node in tree.body:
        for name in _assignment_names(node):
            if name not in found:
                found[name] = node
    return found


def source_slice(lines: list[str], node: ast.AST) -> str:
    """Фрагмент исходника для узла (1-based lineno/end_lineno)."""
    start = int(node.lineno) - 1
    end = int(getattr(node, "end_lineno", node.lineno))
    return "".join(lines[start:end]).rstrip() + "\n"


def sync_pair(example_path: Path, settings_path: Path) -> list[str]:
    """Дописать missing ключи. Возвращает список добавленных имён."""
    if not example_path.is_file():
        raise FileNotFoundError(f"нет шаблона: {example_path}")
    if not settings_path.is_file():
        raise FileNotFoundError(f"нет settings: {settings_path}")

    example_text = example_path.read_text(encoding="utf-8")
    settings_text = settings_path.read_text(encoding="utf-8")
    example_lines = example_text.splitlines(keepends=True)

    example_tree = ast.parse(example_text, filename=str(example_path))
    settings_tree = ast.parse(settings_text, filename=str(settings_path))

    example_assigns = collect_top_level_assigns(example_tree)
    settings_names = set(collect_top_level_assigns(settings_tree))

    missing: list[str] = []
    snippets: list[str] = []
    for name, node in example_assigns.items():
        if name in settings_names:
            continue
        missing.append(name)
        snippets.append(source_slice(example_lines, node))

    if not missing:
        return []

    addition = "\n" + MARKER + "\n" + "".join(snippets)
    if not settings_text.endswith("\n"):
        addition = "\n" + addition
    settings_path.write_text(settings_text + addition, encoding="utf-8")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Дописать недостающие ключи settings.py из settings.example.py"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Корень проекта (папка с bot/)",
    )
    parser.add_argument(
        "--dir",
        action="append",
        dest="dirs",
        help="Относительный путь модуля (можно несколько раз). По умолчанию — все.",
    )
    args = parser.parse_args(argv)

    root: Path = args.project_root.resolve()
    dirs = args.dirs if args.dirs else list(DEFAULT_DIRS)

    any_error = False
    for rel in dirs:
        rel_norm = rel.replace("\\", "/")
        example = root / rel_norm / "settings.example.py"
        settings = root / rel_norm / "settings.py"
        label = rel_norm.replace("/", "\\")
        try:
            added = sync_pair(example, settings)
        except FileNotFoundError as exc:
            print(f"[!] {label}: {exc}")
            continue
        except SyntaxError as exc:
            print(f"[ОШИБКА] {label}: синтаксис — {exc}")
            any_error = True
            continue
        except OSError as exc:
            print(f"[ОШИБКА] {label}: {exc}")
            any_error = True
            continue

        if added:
            print(f"[OK] {label}: добавлены {', '.join(added)}")
        else:
            print(f"[OK] {label}: уже актуален")

    return 1 if any_error else 0


if __name__ == "__main__":
    sys.exit(main())
