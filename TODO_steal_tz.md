# Модуль кражи — техническая спецификация

> Полное техническое описание **текущей** реализации.  
> Продуктовые правила: [`TODO_steal.md`](TODO_steal.md).  
> **Актуально:** 2026-08-04 · миграция `m028_steal_rework` (schema ≥ 28)

---

## 1. Обзор

Модуль реализует чат-команды `!кража` / `!карман` / `!срок` (тюрьма общая), расписание ср/пт (МСК), ручной override из админки, прокачку шанса, тиры лута, джекпот из `minigames_bank`, возврат при посадке и админ-API для статы и тиров.

| Слой | Ответственность |
|------|-----------------|
| Команды | `bot/princess/commands/steal.py`, `info.py` |
| Математика | `bot/princess/economy.py` |
| Константы | `bot/princess/settings.py` (+ `settings.example.py`) |
| Оркестрация / тики | `bot/princess/handler.py`, `StealStore` в `storage.py` |
| БД | `bot/db/steal.py`, `steal_meta.py`, миграция `m028` |
| Админ API / UI | `bot/web/routes/admin.py`, `obs/admin.html`, `obs/admin.js` |
| Сейф | `bot.fishing.has_steal_safe` |
| Тюрьма | `bot/princess/prison.py` + `bot/db/prison.py` |

---

## 2. Карта файлов

| Файл | Роль |
|------|------|
| [`bot/princess/settings.example.py`](bot/princess/settings.example.py) | Шаблон баланса; боевой `settings.py` локальный (не в git) |
| [`bot/princess/economy.py`](bot/princess/economy.py) | Рост/спад шанса, тиры, `roll_steal_amount`, `prison_chance_for_amount`, дни расписания |
| [`bot/princess/commands/steal.py`](bot/princess/commands/steal.py) | Поток `!кража`, короткие тексты |
| [`bot/princess/commands/info.py`](bot/princess/commands/info.py) | `!карман`, `!срок` |
| [`bot/princess/storage.py`](bot/princess/storage.py) | `StealStore`: transfer/revert, bank, loot tiers, stats, miss-decay batch |
| [`bot/princess/handler.py`](bot/princess/handler.py) | Роутинг команд, `_steal_watch_loop`, miss-decay тик, анонсы, admin open/close |
| [`bot/db/steal.py`](bot/db/steal.py) | CRUD `steal_stats`, success/revert/jail |
| [`bot/db/steal_meta.py`](bot/db/steal_meta.py) | Override расписания, `last_miss_decay_day_key`, `loot_tiers_json` |
| [`bot/db/migrations/m028_steal_rework.py`](bot/db/migrations/m028_steal_rework.py) | Бэкап + wipe stats + колонки |
| [`bot/web/routes/admin.py`](bot/web/routes/admin.py) | `/api/steal*` |
| [`obs/admin.html`](obs/admin.html) / [`obs/admin.js`](obs/admin.js) | Вкладка «Кража» |
| [`scripts/test_steal_economy.py`](scripts/test_steal_economy.py) | Юнит-проверки роста/спада/лута |

---

## 3. Константы

Источник правды: `bot/princess/settings.py` (копия с example).

```python
STEAL_MIN_VIEWERS = 5
STEAL_COOLDOWN_SEC = 600
STEAL_ALLOWED_WEEKDAYS = (2, 4)  # ср, пт (MSK weekday)
STEAL_ROLL_MAX = 100

VICTIM_MIN_BALANCE = 3000
STEAL_AMOUNT_FLOOR = 100

STEAL_BANK_JACKPOT_CHANCE = 0.01
STEAL_BANK_AMOUNT_MULT = 2

STEAL_CHANCE_FLOOR = 5
STEAL_CHANCE_CAP = 35
STEAL_CHANCE_ATTEMPTS_DIV = 5   # +1% каждые N попыток
STEAL_DECAY_MISSED_DAY_PCT = 2

STEAL_LOOT_TIER_KEYS = ("meloch", "normal", "zhir", "kush")
STEAL_LOOT_TIERS = (
    (50, 100, 400),   # meloch
    (30, 400, 900),   # normal
    (15, 900, 1600),  # zhir
    (5, 1600, 2500),  # kush
)

PRISON_CHANCE_TIERS = (
    (100, 399, 5),
    (400, 899, 12),
    (900, 1599, 20),
    (1600, 2500, 30),
    (2501, 5000, 35),
)
PRISON_DURATION_SEC = 30 * 60
```

Перед продом сверить локальный `settings.py`: не оставлять тестовые `STEAL_COOLDOWN_SEC = 1` / `STEAL_MIN_VIEWERS = 2`.

---

## 4. Схема БД

### 4.1. `steal_stats`

| Колонка | Тип | Смысл |
|---------|-----|--------|
| `user_id` | TEXT PK | GG user id |
| `attempts` | INT | Число вызовов `!кража` (после прохождения CD) |
| `success` | INT | Число реальных списаний (не откатывается при тюрьме) |
| `stolen_total` | INT | Нетто унесённое (минус возвраты) |
| `chance` | INT | Текущий шанс % (явно; дефолт **5**) |
| `last_time` | REAL | unix time последней попытки (CD) |
| `times_in_jail` | INT | Отсидки из кражи |
| `last_steal_day_key` | TEXT | `YYYY-MM-DD` (МСК) последнего `!кража` |

Строка создаётся через `ensure_user` при первой команде.

### 4.2. `steal_meta` (одна строка `id = 1`)

| Колонка | Тип | Смысл |
|---------|-----|--------|
| `override_enabled` | INT | Бессрочное ручное открытие |
| `override_until` | REAL NULL | unix time конца timed-open |
| `last_schedule_open_key` | TEXT | День, за который уже анонсировали «день кражи» |
| `last_miss_decay_day_key` | TEXT | День ср/пт, за который уже прогнали miss-decay |
| `loot_tiers_json` | TEXT NULL | Override тиров; NULL = дефолты settings |

### 4.3. Миграция `m028_steal_rework`

Порядок:

1. `SELECT * FROM steal_stats` → JSON  
   `data/backups/steal_stats_wipe_YYYYMMDD.json`  
   формат: `{"wiped_at": "<ISO MSK>", "rows": [...]}`.
2. `DELETE FROM steal_stats`.
3. `ALTER` / ensure: `steal_stats.last_steal_day_key`.
4. `ALTER` / ensure: `steal_meta.last_miss_decay_day_key`, `loot_tiers_json`.

Не трогает: `points`, `prison`, `user_cards`, значения override расписания.

**Важно для `init_schema`:** `INSERT OR IGNORE INTO steal_meta` должен использовать только колонки, существующие **до** m028 (`override_*`, `last_schedule_open_key`). Иначе на БД schema 27 открытие падает до `run_migrations`. Новые колонки добавляет миграция; `TABLES_SQL` описывает полный вид для свежих БД.

---

## 5. Математика (`economy.py`)

### 5.1. Рост шанса

```python
def apply_attempt_growth(info: dict) -> None:
    # после info['attempts'] += 1
    if attempts <= 0 or attempts % STEAL_CHANCE_ATTEMPTS_DIV != 0:
        return
    info["chance"] = min(STEAL_CHANCE_CAP, int(chance or FLOOR) + 1)
```

Нельзя каждый каст делать `chance = f(attempts)` — это затрёт miss-decay.

Хелпер (тесты/отображение, не runtime-истина после decay):

```python
chance_ceiling_from_attempts(attempts) =
    min(CAP, FLOOR + attempts // ATTEMPTS_DIV)
```

### 5.2. Missed-day decay

```python
def apply_missed_day_decay(info: dict, day_key: str) -> bool:
    if info["last_steal_day_key"] == day_key:
        return False
    if chance <= FLOOR:
        return False
    info["chance"] = max(FLOOR, chance - STEAL_DECAY_MISSED_DAY_PCT)
    return True
```

Тик в `PrincessHandler._process_missed_day_decay`:

- `yesterday = today_msk - 1 day`;
- если `yesterday.weekday() ∉ STEAL_ALLOWED_WEEKDAYS` → выход;
- если `last_miss_decay_day_key == yesterday` → выход;
- иначе batch по всем `steal_stats`, затем записать ключ в meta.

Ручной override-день **не** триггерит miss. Проверка ~раз в час (`_steal_next_wake_delay` включает 3600 с) и на полуночных пробуждениях.

### 5.3. Лут

Эффективные тиры: `StealStore.get_loot_tiers()` → `effective_loot_tiers(meta.loot_tiers)`:

1. parse `loot_tiers_json`;
2. валидация: 4 ключа, `weight ≥ 0`, `sum(weights) > 0`, `min ≤ max`;
3. иначе `STEAL_LOOT_TIERS`.

`roll_steal_amount(tiers)` — взвешенный выбор диапазона, затем `randint(lo, hi)`.

Формат JSON override:

```json
{
  "meloch": {"weight": 50, "min": 100, "max": 400},
  "normal": {"weight": 30, "min": 400, "max": 900},
  "zhir": {"weight": 15, "min": 900, "max": 1600},
  "kush": {"weight": 5, "min": 1600, "max": 2500}
}
```

### 5.4. Тюрьма

`prison_chance_for_amount(stolen)` — линейный поиск по `PRISON_CHANCE_TIERS`; вне диапазонов → 0 (тюрьмы нет).

---

## 6. Поток `cmd_steal`

```text
if not StealStore.is_allowed(): short; return
refresh viewers; if len < MIN: short; return

mutate_info:
  if CD: short; return
  last_time = now
  attempts += 1
  last_steal_day_key = today_msk
  apply_attempt_growth(info)
  chance = info.chance

if d100 > chance: "Провал."; return

tiers = get_loot_tiers()
bank_jackpot = false

if random() < JACKPOT_CHANCE:
  desired = roll_steal_amount(tiers) * BANK_MULT
  taken = execute_bank_steal(..., min_required=FLOOR*MULT)
  if taken: bank_jackpot = true; stolen = taken

if not bank_jackpot:
  victim = random(viewers \ {self})
  if none: short; return
  if bal < 3000: poor; return          # без тюрьмы
  if steal_safe: safe; return          # без тюрьмы
  amount = min(roll_steal_amount(tiers), bal - 3000)
  if amount < FLOOR: short; return
  execute_steal(...); stolen = amount

if prison roll (d100 <= prison_chance_for_amount(stolen)):
  revert_steal / revert_bank_steal
  imprison; jail++
  "Поймали! Вернули N. Тюрьма M мин."
else:
  "Унёс N у Name" | "Джекпот! N из казны."
```

### 6.1. Transfer / revert

| Метод | Действие |
|-------|----------|
| `execute_steal` | `points.transfer(victim→thief)` + `record_steal_success` |
| `revert_steal` | `transfer(thief→victim)` + `record_steal_reverted` |
| `execute_bank_steal` | `try_withdraw` bank + `points.add(thief)` + success |
| `revert_bank_steal` | `points.add(thief, -amount)` + `add_bank` + reverted |

`record_steal_reverted`: `stolen_total = max(0, stolen_total - amount)`; **success не трогать**.

### 6.2. Доступность (`is_allowed`)

`True`, если:

- сегодня weekday ∈ `STEAL_ALLOWED_WEEKDAYS`, **или**
- `override_enabled`, **или**
- `override_until > now`.

---

## 7. `!карман`

`cmd_pocket` читает `get_info` **без** пересчёта шанса:

```
Попыток / Успехов / Унесено / Отсидки / Шанс: C%
```

---

## 8. Фоновые задачи (`handler`)

| Событие | Действие |
|---------|----------|
| `_steal_watch_loop` | process events → sleep `min(до полуночи МСК, 1ч, до override_until)` |
| Истёк `override_until` | clear timer; анонс «Кража закрыта», если нет schedule/бессрочного override |
| Новый день расписания | анонс «Сегодня день кражи…»; `last_schedule_open_key` |
| Конец дня расписания | анонс «Следующий — {день}» |
| Miss-decay | см. §5.2 |
| `!кража` | `last_steal_day_key = today_msk` |

Анонсы дня кражи ретраятся коротко, пока GG не подключён (`last_schedule_open_key != today`).

Тюрьма: в `handle_message` до роутинга — если в prison, только `!срок` (остальные `!` — отказ).

---

## 9. Админ API и UI

### 9.1. API

| Метод | Путь | Назначение |
|-------|------|------------|
| `GET` | `/api/steal` | Статус расписания / override |
| `PUT` | `/api/steal` | `{override_enabled}` или `{duration_hours}` |
| `GET` | `/api/steal/stats` | `{players, count}` |
| `GET` | `/api/steal/loot-tiers` | `{is_default, tiers, defaults}` |
| `PUT` | `/api/steal/loot-tiers` | body `{tiers: {...}}` или сам объект тиров |
| `POST` | `/api/steal/loot-tiers/reset` | `loot_tiers_json = NULL` |

Элемент stats: `user_id`, `user_name`, `attempts`, `success`, `stolen_total`, `chance`, `times_in_jail`, `last_steal_day_key`, `last_time`.  
Сортировка SQL: `chance DESC`, `stolen_total DESC`, `attempts DESC`.

Валидация PUT тиров: 4 ключа, `weight ≥ 0`, `sum > 0`, `min ≤ max` → иначе 400.

Ответ loot: у каждого тира поле `pct` (доля веса).

### 9.2. UI (`obs/admin.html` вкладка «Кража»)

1. Open / Close / Timed + Refresh.
2. Таблица тиров: вес, %, min, max; Save / Reset.
3. Таблица `steal_stats` (readonly).

Refresh грузит status + loot + stats параллельно.

---

## 10. Связанные таблицы / модули

| Зависимость | Использование |
|-------------|----------------|
| `points` / `PointsStore` | Балансы, transfer, flush_pending |
| `minigames_bank` | Джекпот withdraw / add_bank |
| `user_names` | Ник в админ-таблице |
| `prison` | imprison / is_in_prison / `!срок` |
| fishing steal_safe | `has_steal_safe(db, victim_id)` |

---

## 11. Тесты

Автомат: `python scripts/test_steal_economy.py`

- рост: attempts 5 → chance 6; 10 → 7; ceiling 150 = CAP;
- miss: 20 → 18; при совпадении day_key — без изменений; у пола 5 не ниже;
- parse loot: sum(weights)=0 → None; валидный dict → roll в [100, 2500].

Миграции: `python scripts/migrate_db.py` (бот должен быть остановлен на Windows).

### Ручной смоук

1. Schema 28; `steal_stats` после m028 пуста (или только новые игроки); бэкап JSON читается.
2. Первая `!кража`: attempts=1, chance=5.
3. После 5 попыток: chance=6; после 10: 7.
4. chance=20, `last_steal_day_key` ≠ вчерашняя ср → после тика miss → 18; у 5 не ниже.
5. Жертва &lt; 3000 → короткий отказ, без тюрьмы.
6. Успех + тюрьма → балансы жертвы как до кражи; вор в тюрьме; `stolen_total` уменьшен; success не −1.
7. Сейф → срыв без тюрьмы.
8. `!карман` — 5 строк, без «осталось N».
9. CD 10 мин; джекпот+тюрьма → возврат в казну.
10. Админка: строки stats после игры; вес куш↑ → жирнее суммы; reset → 50/30/15/5.
11. PUT sum(weights)=0 → 400, БД цела.

---

## 12. Операционка

| Действие | Как |
|----------|-----|
| Накатить миграции без бота | `python scripts/migrate_db.py` |
| Бэкап вайпа статы | `data/backups/steal_stats_wipe_*.json` |
| Подкрутить жирность | Админка → тиры; или `settings` дефолты после reset |
| Открыть вне ср/пт | Админка Open / Open N ч |
| Локальный тест CD | Временно `STEAL_COOLDOWN_SEC` / `STEAL_MIN_VIEWERS` в `settings.py`; **не** коммитить |

Анонс игрокам (выкат): вайп статы, кап 35%, пол жертвы 3к, возврат при тюрьме, −2% за пропуск ср/пт.

---

## 13. Риски и инварианты

| Риск | Митигация |
|------|-----------|
| INSERT meta с новыми колонками до m028 | INSERT только старых колонок в `schema.init` / `ensure_meta` |
| Miss дважды за день | `last_miss_decay_day_key` |
| `chance = f(attempts)` затирает спад | только `apply_attempt_growth` |
| Битый JSON тиров | fallback на settings |
| Тестовый CD=1 в проде | сверка с example |
| Длинные ответы | короткие шаблоны в `steal.py` / `info.py` |

---

## 14. Вне текущего скоупа

- Выбор жертвы только среди eligible balance.
- Ручная правка `chance` / `attempts` игрока из админки.
- Иммунитет жертвы после N краж за стрим.
- Недельный soft-decay / кап 70% (удалены).
- Изменение пассива / цен бустеров ради кражи.

---

## 15. Чеклист внедрения (закрыт)

- [x] Константы и математика
- [x] БД m028 + wipe + поля
- [x] `cmd_steal` + revert + короткие тексты
- [x] `!карман` + miss-тик
- [x] Админка stats + loot tiers
- [x] README / бизнес-логика / этот документ
- [ ] Анонс в чат при необходимости
- [ ] Смоук в ближайший день кражи
