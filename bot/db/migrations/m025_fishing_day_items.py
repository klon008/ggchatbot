"""Migration 025: day items — mermaid shields + bite boost casts."""

from __future__ import annotations

import aiosqlite

VERSION = 25
DESCRIPTION = (
    "Колонки mermaid_shields и bite_boost_casts_left в fishing_players"
)


async def upgrade(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(fishing_players)") as cursor:
        cols = await cursor.fetchall()
    col_names = {c[1] for c in cols}
    if "mermaid_shields" not in col_names:
        await conn.execute(
            "ALTER TABLE fishing_players "
            "ADD COLUMN mermaid_shields INTEGER NOT NULL DEFAULT 0"
        )
    if "bite_boost_casts_left" not in col_names:
        await conn.execute(
            "ALTER TABLE fishing_players "
            "ADD COLUMN bite_boost_casts_left INTEGER NOT NULL DEFAULT 0"
        )
