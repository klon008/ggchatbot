from __future__ import annotations

import re
from pathlib import Path


def ensure_markers(text: str, start: str, end: str, insert_before: str | None = None) -> str:
    """Ensure marker region exists; return updated text."""
    if start in text and end in text:
        return text
    block = f"\n{start}\n{end}\n"
    if insert_before and insert_before in text:
        return text.replace(insert_before, block + insert_before, 1)
    return text.rstrip() + block


def replace_marked(text: str, start: str, end: str, body: str) -> str:
    pattern = re.compile(
        re.escape(start) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    replacement = f"{start}\n{body.rstrip()}\n{end}"
    if not pattern.search(text):
        raise ValueError(f"Markers not found: {start} … {end}")
    return pattern.sub(replacement, text, count=1)


def camel_import_name(card_id: str) -> str:
    parts = card_id.replace("-", "_").split("_")
    return parts[0] + "".join(p.title() for p in parts[1:]) + "Img"


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")
