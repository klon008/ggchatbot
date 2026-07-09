# README_SQL — персистентность бота в SQLite

Документ описывает миграцию с JSON-файлов на единую базу **`data/bot.db`**, схему таблиц, поведение слоя `bot/db/` и порядок перехода с существующих данных.

Общая архитектура бота — в [README_DEV.md](README_DEV.md).

---

## Содержание

1. [Что изменилось](#1-что-изменилось)
2. [Файлы и зависимости](#2-файлы-и-зависимости)
3. [Режим WAL и PRAGMA](#3-режим-wal-и-pragma)
4. [Схема таблиц](#4-схема-таблиц)
5. [Архитектура слоя `bot/db`](#5-архитектура-слоя-botdb)
6. [Публичный API stores (без изменений для handlers)](#6-публичный-api-stores-без-изменений-для-handlers)
7. [Особенности реализации](#7-особенности-реализации)
8. [Миграция с JSON](#8-миграция-с-json)
9. [Эксплуатация и бэкапы](#9-эксплуатация-и-бэкапы)
10. [Типичные проблемы](#10-типичные-проблемы)

---

## 1. Что изменилось

| Было (JSON) | Стало (SQLite) |
|-------------|----------------|
| `data/princess_points.json` | таблица `points` |
| `data/steal_chance_and_count.json` | таблица `steal_stats` |
| `data/daily_bonus.json` | таблицы `daily_meta`, `daily_progress`, `daily_claims` |
| `data/queue.json` | таблицы `queue_meta`, `queue_items` |
| тюрьма in-memory (`prison.py`) | таблица `prison` |
| кулдаун кубика in-memory | таблица `dice_cooldowns` |

**Не переносилось в SQLite (by design):**

- кулдаун `!sr` между заказами (`USER_COOLDOWN_SEC`) — по-прежнему in-memory в `SongRequestHandler`;
- после рестарта бота этот кулдаун сбрасывается.

**Убрано:**

- `JsonStore`, атомарная запись `*.json.tmp` → `os.replace()`;
- legacy-миграция JSON из корня проекта в `data/`;
- `flush()` при shutdown — для SQLite не нужен (запись идёт сразу).

**Добавлено:**

- атомарная кража (`execute_steal`) — перевод баллов и обновление статистики в одной транзакции;
- персистентная тюрьма и кулдаун `!дайс` — переживают рестарт.

---

## 2. Файлы и зависимости

### Рабочий файл

```
data/bot.db          # единая БД (в .gitignore)
data/bot.db-wal      # WAL-журнал (создаётся автоматически)
data/bot.db-shm      # shared memory (создаётся автоматически)
```

### Зависимость

```
aiosqlite>=0.20,<1.0
```

в `requirements.txt`. Драйвер **async** — не блокирует event loop бота.

### Код

```
bot/db/
  connection.py    # Database: open/close, PRAGMA, transaction()
  schema.py          # CREATE TABLE, версия схемы
  points.py
  steal.py
  daily.py
  queue.py
  prison.py
  cooldowns.py

bot/princess/storage.py   # тонкие обёртки PointsStore / StealStore / DailyStore / DiceCooldownStore
bot/song_request/queue.py # QueueManager (async, SQL внутри)
bot/princess/prison.py    # PrisonManager (async, SQL внутри)

scripts/migrate_json_to_sqlite.py   # одноразовая миграция JSON → bot.db
```

### Жизненный цикл

`StreamBot` в `bot/app.py`:

1. `await db.open()` — в начале `run()`;
2. handlers получают один общий экземпляр `Database`;
3. `await db.close()` — в `close()` после остановки модулей.

Бот **не** делает auto-migrate при старте. Если в `data/` лежат старые JSON — сначала запустите миграционный скрипт (см. [§8](#8-миграция-с-json)).

---

## 3. Режим WAL и PRAGMA

При каждом `Database.open()` выполняется:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

### Зачем WAL

- Частые мелкие записи (`+5` за сообщение, пассивный доход, `!sr`, кража) — меньше блокировок, чем в режиме `DELETE`.
- Лучше переживает краш: незавершённые транзакции откатываются, уже закоммиченные данные в порядке.
- Один процесс бота, но параллельные async-задачи (пассивный доход + чат + очередь) — WAL даёт более мягкую конкурентность читатель/писатель.

WAL **включён всегда** — это не опциональная оптимизация, а штатный режим для этого проекта.

### Ограничение на Windows

Не открывайте `bot.db` в DB Browser / DBeaver / другом GUI-редакторе, пока работает `python main.py`. Иначе возможна ошибка `database is locked`.

---

## 4. Схема таблиц

Версия схемы: **1** (`schema_version`).

### Princess — экономика

```sql
-- Балансы принцесс
CREATE TABLE points (
    user_id TEXT PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0
);

-- Статистика краж
CREATE TABLE steal_stats (
    user_id TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 0,
    stolen_total INTEGER NOT NULL DEFAULT 0,
    chance INTEGER NOT NULL DEFAULT 3,
    last_time REAL NOT NULL DEFAULT 0,
    times_in_jail INTEGER NOT NULL DEFAULT 0
);

-- Текущий месяц для !дейлик
CREATE TABLE daily_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_month TEXT NOT NULL DEFAULT ''   -- 'YYYY-MM'
);

-- Счётчик использований !дейлик в месяце
CREATE TABLE daily_progress (
    user_id TEXT NOT NULL,
    month TEXT NOT NULL,
    counter INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, month)
);

-- Кто уже забрал дейлик в конкретный день
CREATE TABLE daily_claims (
    user_id TEXT NOT NULL,
    day TEXT NOT NULL,                       -- 'YYYY-MM-DD'
    PRIMARY KEY (user_id, day)
);

-- Тюрьма (30 мин)
CREATE TABLE prison (
    user_id TEXT PRIMARY KEY,
    release_time REAL NOT NULL
);

-- Кулдаун !дайс (5 мин)
CREATE TABLE dice_cooldowns (
    user_id TEXT PRIMARY KEY,
    last_time REAL NOT NULL
);
```

### Song request — очередь

```sql
-- Метаданные очереди (одна строка id=1)
CREATE TABLE queue_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_json TEXT,           -- JSON текущего Track или NULL
    current_token TEXT,          -- 't-1', 't-2', ...
    token_counter INTEGER NOT NULL DEFAULT 1
);

-- Ожидающие треки (0-based position)
CREATE TABLE queue_items (
    position INTEGER PRIMARY KEY,
    video_id TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_by_name TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    added_at REAL NOT NULL
);
```

### Соответствие старым JSON

| JSON-ключ / файл | SQLite |
|------------------|--------|
| `princess_points.json` → `{user_id: balance}` | `points` |
| `steal_chance_and_count.json` → объект на user | `steal_stats` |
| `daily_bonus.json` → `current_month` | `daily_meta` |
| `daily_bonus.json` → `user_progress` | `daily_progress` |
| `daily_bonus.json` → `"YYYY-MM-DD": [uids]` | `daily_claims` |
| `queue.json` → `current` | `queue_meta.current_json` + `current_token` |
| `queue.json` → `queue[]` | `queue_items` |

---

## 5. Архитектура слоя `bot/db`

```
StreamBot
  └── Database (одно соединение aiosqlite)
        ├── PrincessHandler
        │     ├── PointsStore      → bot/db/points.py
        │     ├── StealStore       → bot/db/steal.py
        │     ├── DailyStore       → bot/db/daily.py
        │     ├── DiceCooldownStore → bot/db/cooldowns.py
        │     └── PrisonManager    → bot/db/prison.py
        └── SongRequestHandler
              └── QueueManager     → bot/db/queue.py
```

### `Database` (`connection.py`)

| Метод | Назначение |
|-------|------------|
| `open()` | Создать `data/`, подключиться, PRAGMA, `init_schema()` |
| `close()` | Закрыть соединение |
| `execute()` / `fetchone()` / `fetchall()` | Одиночные запросы с `asyncio.Lock` + commit |
| `transaction()` | Context manager: `BEGIN` → yield `conn` → `COMMIT` / `ROLLBACK` |

Все операции сериализуются через `asyncio.Lock` на одном connection — для однопроцессного бота этого достаточно.

---

## 6. Публичный API stores (без изменений для handlers)

Handlers (`princess/handler.py`, `song_request/handler.py`) по-прежнему работают с теми же классами:

### `PointsStore`

```python
await points.add(user_id, amount) -> int      # новый баланс
await points.get_balance(user_id) -> int
await points.set_balance(user_id, amount)
```

### `StealStore`

```python
await steal.get_info(user_id) -> dict
async with steal.mutate_info(user_id) as info: ...
await steal.execute_steal(thief_id, victim_id, amount)   # атомарно
await steal.increment_jail_count(user_id)
```

### `DailyStore`

```python
async with daily.mutate() as data:
    # data эмулирует старый JSON-dict:
    # current_month, user_progress, "YYYY-MM-DD": [user_ids...]
```

### `DiceCooldownStore`

```python
await dice_cooldowns.get_last(user_id) -> float
await dice_cooldowns.set_last(user_id, timestamp)
```

### `QueueManager` (изменение: методы стали async)

```python
await queue.load()                    # в SongRequestHandler.start()
await queue.add(track) -> int
await queue.start_next() -> (Track, token) | None
await queue.finish_current(token) -> bool
await queue.force_skip()
await queue.clear()
```

`load()` / `flush()` / `normalize()` у princess-stores — no-op (совместимость с `start()` / `close()`).

---

## 7. Особенности реализации

### Атомарная кража

Раньше кража делала три отдельные записи (баланс жертвы, баланс вора, steal stats) без общей транзакции. Теперь `StealStore.execute_steal()` вызывает `bot/db/steal.py::execute_steal()`:

1. `BEGIN`
2. `points` victim −= amount, thief += amount
3. `steal_stats` success += 1, stolen_total += amount
4. `COMMIT`

Попытка кражи (кулдаун, `attempts`, `last_time`, `chance`) по-прежнему обновляется отдельно через `mutate_info()` **до** броска на успех.

### Очередь и crash recovery

Поведение как у старого `queue.json`:

- во время воспроизведения `current` и `queue` хранятся раздельно;
- при **загрузке** (`QueueManager.load()`): если в `queue_meta` есть `current_json`, трек возвращается **в голову** `_queue` (как после краша в JSON-версии);
- `current_token` и `token_counter` персистентны в `queue_meta`.

### Тюрьма

`PrisonManager.is_in_prison()` при проверке удаляет просроченные записи (`release_time <= now()`).

### Daily

`DailyStore.mutate()` загружает snapshot из SQL в dict, handler меняет dict как раньше, при выходе из context manager данные пишутся обратно в `daily_meta` / `daily_progress` / `daily_claims`.

---

## 8. Миграция с JSON

### Когда нужна

Если в `data/` ещё есть рабочие файлы:

- `princess_points.json`
- `steal_chance_and_count.json`
- `daily_bonus.json`
- `queue.json`

и вы хотите сохранить данные.

### Команда

```powershell
python scripts/migrate_json_to_sqlite.py
```

### Что делает скрипт

1. **Бэкап** — копия `data/` → `data/backup-YYYYMMDD-HHMMSS/` (без `*.db` и старых backup-папок).
2. **Создание** `data/bot.db` (если уже есть — удаляется и создаётся заново).
3. **Импорт** всех четырёх JSON в таблицы.
4. **Сверка:**
   - сумма балансов JSON == `SUM(points.balance)`;
   - число ключей steal == число строк `steal_stats`;
   - длина очереди (queue + current) совпадает.
5. При успехе — переименование JSON в `*.json.bak` (не удаляются).
6. При ошибке сверки — JSON **не** трогаются, скрипт завершается с кодом 1.

### После миграции

- рабочий файл — только `data/bot.db`;
- JSON остаются как архив (`*.json.bak`) или в `backup-*`;
- бот при старте пишет только в SQLite.

### Чистая установка (без JSON)

Если JSON нет — просто запустите бота. `Database.open()` создаст пустую `bot.db` со схемой.

---

## 9. Эксплуатация и бэкапы

### Бэкап

Скопируйте весь каталог `data/` (или минимум `bot.db` + при необходимости `bot.db-wal` / `bot.db-shm` при остановленном боте):

```powershell
Copy-Item -Recurse data\ data-backup-manual\
```

Для консистентного бэкапа **остановите бота** перед копированием или используйте SQLite `.backup` в остановленном состоянии.

### Восстановление

1. Остановить бота.
2. Заменить `data/bot.db` из бэкапа.
3. Удалить `bot.db-wal` / `bot.db-shm`, если копировали только `.db` после аварийного завершения.
4. Запустить бота.

Альтернатива: восстановить из `data/backup-*` или `*.json.bak` + повторный запуск миграционного скрипта.

### Просмотр данных

```powershell
sqlite3 data\bot.db "SELECT user_id, balance FROM points ORDER BY balance DESC LIMIT 10;"
```

Только при **остановленном** боте или через read-only подключение.

---

## 10. Типичные проблемы

| Симптом | Причина | Решение |
|---------|---------|---------|
| `database is locked` | `bot.db` открыт в GUI или второй процесс | Закрыть редактор, оставить один экземпляр бота |
| Балансы нулевые после «миграции» | JSON уже были `.bak`, скрипт импортировал пустые файлы | Восстановить JSON из `backup-*`, удалить `bot.db`, запустить скрипт снова |
| Очередь «залипла» | Незавершённый `current` при краше | При рестарте трек вернётся в очередь автоматически; или очистить `queue_items` / `queue_meta` |
| Тюрьма «висит» после истечения срока | Запись не удалена до первой проверки | Любая команда от пользователя вызовет `is_in_prison()` и очистит просрочку |
| `no such table` | Старая/битая `bot.db` | Удалить `bot.db`, перезапустить бота (создаст схему) или прогнать миграцию |

---

## Быстрая шпаргалка

```powershell
# Установка зависимости
pip install -r requirements.txt

# Миграция (один раз, если есть JSON)
python scripts/migrate_json_to_sqlite.py

# Запуск бота
python main.py

# Smoke-тест очереди (без GG)
python smoke_test.py
```

```python
from bot.db import Database, default_db_path
from bot.princess.storage import PointsStore

db = Database()
await db.open()
points = PointsStore(db)
balance = await points.get_balance("12345")
await db.close()
```

---

*Документ актуален для схемы версии 1 (`bot/db/schema.py`).*
