# README_DEV_CARDS — коллекционные карты (бот)

Документация для разработчика **Python-бота** (`botmsc` / ggchatbot).  
Параллельный документ фронта: в репозитории сайта `princtascdwk` → [`README_DEV_CARDS.md`](https://github.com/klon008/princtascdwk/blob/main/README_DEV_CARDS.md) (локально: `E:\Work\dartvalkkiprincess\princtascdwk\README_DEV_CARDS.md`).

Механика для людей: [SPEC.md](https://github.com/klon008/princtascdwk/blob/main/SPEC.md). План реализации: [TODO_album.md](./TODO_album.md).

**Обновлено:** 2026-07-14 · схема БД **v11**

---

## 1. Карта мира

| Где | Что |
|-----|-----|
| SQLite (`data/bot.db`) | Источник правды: серии, карты, бустеры, тиражи, альбомы |
| Команды чата | `!бустер`, `!бустер инфо`, `!альбом` → модуль `bot/cards/` |
| OBS Admin | `http://127.0.0.1:8765/admin.html` → вкладка **Карты** (не в туннеле) |
| Album API | `http://127.0.0.1:18770` — только `GET` альбома/health (в CLO) |
| Арты для админки | `obs/assets/cards/{slug}.webp`, рубашки `{back-id}.svg` |
| Описания (лор) | `data/card-assets-repo/src/app/cardDetails.json` ← сайт (только чтение в Admin) |

Фронт рисует портреты из **своего** бандла (`src/imports`). Бот в API отдаёт `id` + метаданные; путь `image_url` нужен админке OBS.

---

## 2. Сущности (словами)

```
Коллекция
  └── Серия (card_series)          ← у серии своя рубашка card_back_id
        └── Карта (cards)          ← slug id, rarity, image_url, series_id

Бустер (boosters)                  ← пул карт (booster_pool)
  └── Тираж / draw (draws)         ← цена, N карт, веса редкостей, active/paused

Альбом игрока (user_cards)         ← (user_id, card_id) UNIQUE
```

- Карта принадлежит **одной** серии.
- Бустер ≠ серия: в пуле могут быть карты из разных серий.
- В момент времени **один** тираж со статусом `active`.

Редкости: `common` · `uncommon` · `rare` · `epic` · `legendary` · `mythic` · `secretRare`.

---

## 3. Как добавить новую принцессу (карту)

Нужен **один и тот же slug** в боте и на сайте (латиница, kebab-case: `snow-white`, `queen-elsa`).

### 3.1 Арт (сайт — источник файла)

1. Положи портрет: `princtascdwk/src/imports/{slug}.webp`
2. Закоммить / задеплой сайт (иначе зрителям не будет картинки).
3. Синхронизируй копию для админки бота:

```powershell
powershell -File scripts\sync-card-assets.ps1
# или локально:
powershell -File scripts\sync-card-assets.ps1 -SrcImports "E:\Work\dartvalkkiprincess\princtascdwk\src\imports"
```

Скрипт вызывается и из `installer\update.ps1`. Кэш GitHub: `data/card-assets-repo` (в `.gitignore`).

`SITE_BASE_URL` — URL GitHub Pages для ссылок `!альбом`: `https://klon008.github.io/princtascdwk/`.  
`CARD_ASSETS_REPO_URL` — явный git-репо артов/лора (опционально; если пусто — вывод из `SITE_BASE_URL` → `https://github.com/klon008/princtascdwk.git`).

### 3.1a Описания (лор)

Источник правды: **сайт** `src/app/cardDetails.json` (ключи = **slug**, поле в `stories`).

- В БД **не** храним.
- В админке **не** редактируем (колонка «описание» — read-only).
- `update.cmd` / `sync-card-assets.ps1` обновляет кэш `data/card-assets-repo` (там же json).
- Бот/админка читают **прямо** `data/card-assets-repo/src/app/cardDetails.json` (без копии в `data/cards/`).
- Workflow: правки у разработчика в git сайта → push → у стримера `update.cmd`. Без `save_cards.cmd`.

См. также `TODO.md` (раздел про лор).

### 3.2 Запись в БД бота

**Вариант A — миграция (правильно для продакшена)**

Новый файл `bot/db/migrations/m0XX_add_card_{slug}.py`:

```python
VERSION = XX
DESCRIPTION = "Карта {slug}"

async def upgrade(conn):
    await conn.execute(
        """
        INSERT OR IGNORE INTO cards (id, series_id, name, rarity, sort_order, image_url)
        VALUES (?, 'fantast', ?, ?, ?, ?)
        """,
        ("my-slug", "Имя", "rare", 28, "/assets/cards/my-slug.webp"),
    )
    await conn.execute(
        "INSERT OR IGNORE INTO booster_pool (booster_id, card_id) VALUES ('start', ?)",
        ("my-slug",),
    )
```

Зарегистрируй в `bot/db/migrations/__init__.py`, обнови `SCHEMA` через миграции.  
Также добавь slug в каталог сида (`m009_elsa_mythic._CATALOG`), чтобы свежие БД получали карту без ручного SQL.

**Вариант B — админка / SQL (быстро на тесте)**

Вставить строку в `cards` + при необходимости в `booster_pool`.  
`image_url` = `/assets/cards/{slug}.webp`.

### 3.3 Фронт (обязательно)

В `princtascdwk` обнови:

- `src/lib/cardCatalog.ts` — import webp, `CATALOG_ORDER`, `NAMES`, `RARITIES`, `PORTRAITS`
- `src/app/cardDetails.json` — `stories[slug]` (модалка на сайте + зеркало у бота)

Без этого API отдаст карту, а сайт её не нарисует (`getCatalogEntry` вернёт `null`).

---

## 4. Как добавить / сменить рубашку серии

Рубашка привязана к **серии**, не к отдельной карте.

| Поле | Смысл |
|------|--------|
| `card_series.card_back_id` | Стабильный id, напр. `card-back` |
| Файл на сайте | `src/imports/{card_back_id}.svg` |
| Файл в боте (админка) | `obs/assets/cards/{card_back_id}.svg` |
| API | у каждой карты и серии: `card_back_id` |

### Шаги

1. Нарисуй SVG → `princtascdwk/src/imports/my-back.svg`
2. На фронте: `src/lib/cardBacks.ts` — import + запись в `CARD_BACKS`
3. Скопируй в бот: `obs/assets/cards/my-back.svg` (или `sync-card-assets.ps1` — копирует `card-back*.svg`)
4. В БД:

```sql
UPDATE card_series SET card_back_id = 'my-back' WHERE id = 'fantast';
```

(или новая миграция).

3D-модалка на сайте берёт `card_back_id` из ответа `GET /api/v1/album` и резолвит через `resolveCardBack()`.

---

## 5. Бустеры и тиражи

| Команда / UI | Назначение |
|--------------|------------|
| `!бустер` | Открыть **активный** тираж |
| `!бустер инфо` | Цена, N карт, promo |
| Admin → Карты | CRUD бустеров, пул, тиражи, promo JPG, лимит/день |

Правила тиража: **не редактируется** после создания — копия → новый id → активировать.  
Дубль: карта не добавляется, возврат `floor((cost/N)*0.25)` баллов.

Стартовый бустер: id `start`, имя **«Стартовый набор»**.

Promo: `POST /api/cards/boosters/{id}/promo` → `obs/assets/boosters/`.

---

## 6. API (кратко)

### Album (порт **18770**, туннель CLO)

| Метод | Путь |
|-------|------|
| GET | `/api/v1/health` |
| GET | `/api/v1/album?u=&k=&exp=` |

Карта в ответе (фрагмент):

```json
{
  "id": "ariel",
  "name": "Ариэль",
  "rarity": "rare",
  "series_id": "fantast",
  "card_back_id": "card-back",
  "d": "2026-07-14",
  "b": "Бустер «Стартовый набор» · Тираж № 001",
  "image_url": "/assets/cards/ariel.webp"
}
```

### Admin (порт **8765**, localhost)

- `GET /api/cards/catalog` · `boosters` · `draws` · `meta`
- `POST/PUT` бустеры, активация/пауза/копия тиража

---

## 7. Ссылка `!альбом` и секреты

```
{SITE_BASE_URL}/?u=nick&k=...&exp=...&api=...
```

| Env | Где | Назначение |
|-----|-----|------------|
| `ALBUM_LINK_SECRET` | `.env` бота | HMAC `k` + AES `api` |
| `VITE_ALBUM_LINK_SECRET` | GitHub Actions secret сайта (как `ALBUM_LINK_SECRET`) | расшифровка `api` на клиенте |
| `SITE_BASE_URL` | `.env` бота | URL GitHub Pages для `!альбом` (`https://klon008.github.io/princtascdwk/`) |
| `CARD_ASSETS_REPO_URL` | `.env` бота | опц. git-репо для sync; иначе вывод из `SITE_BASE_URL` |
| `CLO_TOKEN` | `.env` бота | `clo set token` перед publish |
| `CLO_PUBLIC_URL` | опц. | тесты без clo |

Значения `ALBUM_LINK_SECRET` и `VITE_ALBUM_LINK_SECRET` должны **совпадать**.

---

## 8. Ключевые пути в репо бота

```
bot/cards/                 # команды, draws, CLO, album server
bot/cards/card_stories.py  # чтение data/card-assets-repo/src/app/cardDetails.json
bot/db/cards.py            # SQL-слой
bot/db/migrations/m008…    # таблицы
bot/db/migrations/m009…    # каталог 28 карт + image_url
bot/db/migrations/m010…    # image_url → /assets/cards/
bot/db/migrations/m011…    # card_back_id, имя бустера
obs/assets/cards/          # webp + svg рубашек для Admin
data/card-assets-repo/     # sparse-кэш сайта (imports + cardDetails.json)
obs/admin.html / admin.js  # вкладка «Карты»
scripts/sync-card-assets.ps1
scripts/migrate_db.py
```

---

## 9. Чеклист новой карты

- [ ] `{slug}.webp` в сайте `src/imports`
- [ ] Запись во фронт `cardCatalog.ts` + `stories[slug]` в `cardDetails.json`
- [ ] Миграция/SQL: `cards` + при необходимости `booster_pool`
- [ ] `sync-card-assets.ps1` / update.cmd (арты + json лора)
- [ ] Проверка: Admin → превью и описание; `!бустер` / `!альбом` в чате
