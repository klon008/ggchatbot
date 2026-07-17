"""Database schema initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiosqlite

from .migrations import MIGRATIONS

SCHEMA_VERSION = max(m.VERSION for m in MIGRATIONS)

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS user_names (
    user_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS points (
    user_id TEXT PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS steal_stats (
    user_id TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    stolen_total INTEGER NOT NULL DEFAULT 0,
    chance INTEGER NOT NULL DEFAULT 3,
    last_time REAL NOT NULL DEFAULT 0,
    times_in_jail INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_month TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS daily_progress (
    user_id TEXT NOT NULL,
    month TEXT NOT NULL,
    counter INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, month)
);

CREATE TABLE IF NOT EXISTS daily_claims (
    user_id TEXT NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS queue_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_json TEXT,
    current_token TEXT,
    token_counter INTEGER NOT NULL DEFAULT 1,
    orders_enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS queue_items (
    position INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_by_name TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    added_at REAL NOT NULL,
    paid_cost INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS prison (
    user_id TEXT PRIMARY KEY,
    release_time REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS dice_cooldowns (
    user_id TEXT PRIMARY KEY,
    last_time REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS minigames_bank (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    bank INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS roulette_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    auto_enabled INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'IDLE',
    round_id INTEGER NOT NULL DEFAULT 0,
    round_opened_at REAL,
    closes_at REAL,
    cooldown_until REAL,
    collect_sec INTEGER NOT NULL DEFAULT 60,
    cooldown_sec INTEGER NOT NULL DEFAULT 180,
    last_result TEXT
);

CREATE TABLE IF NOT EXISTS races_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    auto_enabled INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'IDLE',
    round_id INTEGER NOT NULL DEFAULT 0,
    round_opened_at REAL,
    closes_at REAL,
    cooldown_until REAL,
    collect_sec INTEGER NOT NULL DEFAULT 60,
    cooldown_sec INTEGER NOT NULL DEFAULT 180,
    race_delay_sec INTEGER NOT NULL DEFAULT 10,
    last_result TEXT,
    race_progress TEXT,
    fixed_odds TEXT
);

CREATE TABLE IF NOT EXISTS races_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL,
    horse_number INTEGER NOT NULL,
    UNIQUE (round_id, user_id)
);

CREATE TABLE IF NOT EXISTS races_lineup (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    horse_number INTEGER NOT NULL,
    princess_name TEXT NOT NULL,
    UNIQUE (round_id, horse_number)
);

CREATE TABLE IF NOT EXISTS races_princess_stats (
    princess_name TEXT PRIMARY KEY,
    races_count INTEGER NOT NULL DEFAULT 0,
    wins_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS roulette_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL,
    bet_type TEXT NOT NULL,
    bet_payload TEXT NOT NULL,
    UNIQUE (round_id, user_id)
);

CREATE TABLE IF NOT EXISTS poll_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL DEFAULT 'IDLE',
    round_id INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    options TEXT NOT NULL DEFAULT '[]',
    round_opened_at REAL,
    closes_at REAL,
    collect_sec INTEGER NOT NULL DEFAULT 300,
    winning_option INTEGER,
    last_result TEXT
);

CREATE TABLE IF NOT EXISTS poll_bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    amount INTEGER NOT NULL,
    option_index INTEGER NOT NULL,
    UNIQUE (round_id, user_id)
);

CREATE TABLE IF NOT EXISTS card_series (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    card_back_id TEXT NOT NULL DEFAULT 'card-back'
);

CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    series_id TEXT NOT NULL,
    name TEXT NOT NULL,
    rarity TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    image_url TEXT,
    FOREIGN KEY (series_id) REFERENCES card_series(id)
);

CREATE TABLE IF NOT EXISTS boosters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    promo_image_url TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS booster_pool (
    booster_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    PRIMARY KEY (booster_id, card_id),
    FOREIGN KEY (booster_id) REFERENCES boosters(id),
    FOREIGN KEY (card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS draws (
    id TEXT PRIMARY KEY,
    booster_id TEXT NOT NULL,
    name TEXT NOT NULL,
    cost_points INTEGER NOT NULL,
    cards_per_open INTEGER NOT NULL,
    rarity_weights TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    daily_limit INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (booster_id) REFERENCES boosters(id)
);

CREATE TABLE IF NOT EXISTS user_cards (
    user_id TEXT NOT NULL,
    card_id TEXT NOT NULL,
    obtained_at TEXT NOT NULL,
    draw_id TEXT,
    draw_name TEXT,
    booster_id TEXT,
    booster_name TEXT,
    PRIMARY KEY (user_id, card_id),
    FOREIGN KEY (card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS booster_openings (
    opening_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    draw_id TEXT NOT NULL,
    booster_id TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    cost_points INTEGER NOT NULL,
    cards_rolled TEXT NOT NULL,
    total_refund INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_daily_opens (
    user_id TEXT NOT NULL,
    day TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

CREATE TABLE IF NOT EXISTS cards_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    daily_open_limit INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    anim_speed REAL NOT NULL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS fishing_players (
    user_id TEXT PRIMARY KEY,
    user_name TEXT NOT NULL DEFAULT '',
    energy INTEGER NOT NULL DEFAULT 100,
    energy_updated_at REAL NOT NULL DEFAULT 0,
    worms INTEGER NOT NULL DEFAULT 0,
    maggots INTEGER NOT NULL DEFAULT 0,
    rod_state TEXT NOT NULL DEFAULT 'none',
    last_cast_at REAL NOT NULL DEFAULT 0,
    day_key TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fishing_records (
    user_id TEXT NOT NULL,
    species TEXT NOT NULL,
    weight REAL NOT NULL,
    PRIMARY KEY (user_id, species)
);

CREATE TABLE IF NOT EXISTS fishing_week_weights (
    week_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    species TEXT NOT NULL,
    weight REAL NOT NULL,
    achieved_at REAL NOT NULL,
    PRIMARY KEY (week_id, user_id, species)
);

CREATE TABLE IF NOT EXISTS fishing_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    day_key TEXT NOT NULL DEFAULT '',
    first_fish_claimed INTEGER NOT NULL DEFAULT 0,
    current_week_id TEXT NOT NULL DEFAULT '',
    pending_rewards_week_id TEXT NOT NULL DEFAULT ''
);
"""


async def init_schema(
    conn: aiosqlite.Connection,
    *,
    db_path: Optional[Path] = None,
) -> None:
    await conn.executescript(TABLES_SQL)
    await conn.execute(
        "INSERT OR IGNORE INTO schema_version (id, version) VALUES (1, ?)",
        (SCHEMA_VERSION,),
    )
    await conn.execute("INSERT OR IGNORE INTO daily_meta (id, current_month) VALUES (1, '')")
    await conn.execute(
        "INSERT OR IGNORE INTO queue_meta (id, current_json, current_token, token_counter) "
        "VALUES (1, NULL, NULL, 1)"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO minigames_bank (id, bank) VALUES (1, 50000)"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO roulette_meta (id, auto_enabled, state, round_id, collect_sec, cooldown_sec) "
        "VALUES (1, 1, 'IDLE', 0, 60, 180)"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO races_meta (id, auto_enabled, state, round_id, collect_sec, cooldown_sec, race_delay_sec) "
        "VALUES (1, 1, 'IDLE', 0, 60, 180, 10)"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO poll_meta (id, state, round_id, title, options, collect_sec) "
        "VALUES (1, 'IDLE', 0, '', '[]', 300)"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO cards_meta (id, daily_open_limit) VALUES (1, 0)"
    )
    await conn.execute(
        "INSERT OR IGNORE INTO fishing_meta "
        "(id, day_key, first_fish_claimed, current_week_id, pending_rewards_week_id) "
        "VALUES (1, '', 0, '', '')"
    )
    from .migrate import run_migrations
    from .migrations.m009_elsa_mythic import seed_if_empty
    from .migrations.m010_card_asset_urls import upgrade as refresh_card_urls

    await run_migrations(conn, db_path=db_path)
    await seed_if_empty(conn)
    # На актуальной схеме пути image_url всегда /assets/cards/...
    await refresh_card_urls(conn)
    await conn.commit()
