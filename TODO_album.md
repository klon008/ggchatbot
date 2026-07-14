# TODO — коллекционные карты (альбом)

> Техническое задание и план реализации связки **Python-бот** (`botmsc`) + **React-сайт** (`princtascdwk`) + **CLO-туннель** (`clo.exe`).  
> Механика: [SPEC.md](E:/Work/dartvalkkiprincess/princtascdwk/SPEC.md) · [TODO_tech.md](E:/Work/dartvalkkiprincess/princtascdwk/TODO_tech.md)

**Обновлено:** 2026-07-13

---

## Архитектура (принятые решения)

```
Зритель → !альбом
              ↓
https://<user>.github.io/princtascdwk/?u=<nick>&k=<sig>&exp=<unix>&api=<enc>
              ↓ (статика GH Pages)
         React: decrypt api → fetch
              ↓
https://<dynamic-clo-url>/api/v1/album?u=&k=&exp=
              ↓ (CLO туннель)
         127.0.0.1:18770 (Album API, read-only)
              ↓
         SQLite (источник правды)
```

| Компонент | Порт / URL | Назначение |
|-----------|------------|------------|
| OBS + админка | `127.0.0.1:8765` (`OBS_WS_PORT`) | player, admin, roulette — **не в туннеле** |
| Album API | `127.0.0.1:18770` (константа в коде) | только `GET /api/v1/album`, `GET /api/v1/health` |
| CLO | туннель → `18770` | динамический публичный HTTPS URL каждый стрим |
| GitHub Pages | `github.io/princtascdwk/` | UI + арты; **без** `VITE_API_BASE_URL` |

**Порт `18770`** — не 8080, не 8765, не выносим в `.env`.

**CLO:** `clo publish http 18770` — протокол `http`, адрес = порт Album API.

**CORS:** только на Album API (`18770`), не на OBS-порт. Неизбежен для `github.io` → домен CLO.

---

## Формат ссылки `!альбом`

```
https://<user>.github.io/princtascdwk/?u=<nick>&k=<sig>&exp=<unix>&api=<enc>
```

| Параметр | Кто создаёт | Смысл |
|----------|-------------|-------|
| `u` | бот | lowercase nick |
| `k` | бот | HMAC-SHA256(`ALBUM_LINK_SECRET`, `u:exp`) → первые 16 символов base64url |
| `exp` | бот | TTL подписи (**24 ч**) |
| `api` | бот | AES-256-GCM шифрование полного base URL CLO, вывод base64url |

**Расшифровка на фронте:** Web Crypto API, ключ = SHA-256(`VITE_ALBUM_LINK_SECRET`).

**Fallback dev:** если `api` отсутствует — `fetch` на `http://127.0.0.1:18770`.

---

## Часть 1 — Бот (`botmsc`)

### 1.1 База данных (миграция `m008_cards`)

Таблицы:

- `card_series` — серия MVP «Фантастический коллекционер»
- `cards` — 27 карт (slug, name, rarity, series_id)
- `boosters`, `booster_pool`, `draws` (тиражи)
- `user_cards` — `(user_id, card_id)` UNIQUE
- `booster_openings` — аудит открытий

Seed: 27 slug из TODO_tech §6.1.

### 1.2 Модуль `bot/cards/`

```
bot/cards/
  constants.py      # ALBUM_API_PORT = 18770, SITE_BASE_URL
  catalog.py
  draws.py          # активный тираж, roll, дубли (floor 25%)
  album_token.py    # build/verify k + encode/decode api URL
  handler.py        # !бустер, !альбом, !бустер инфо
  clo_tunnel.py     # subprocess clo.exe
  album_server.py   # второй LocalWebServer + CORS
  routes/album.py
```

### 1.3 Album HTTP API (порт 18770)

| Метод | Путь | Поведение |
|-------|------|-----------|
| GET | `/api/v1/health` | `{ "ok": true }` |
| GET | `/api/v1/album?u=&k=&exp=` | verify token → JSON |

CORS + rate limit (60 req/min по IP).

### 1.4 CLO-туннель

- Бинарь в репо: `tools/clo/clo.exe` (версия через `clo upgrade`)
- `CLO_TOKEN` в `.env` → перед publish: `clo set token …`
- spawn при `StreamBot.run()`, terminate при `close()`
- Любая ошибка CLO → красный CRITICAL + остановка старта бота (кроме `CLO_PUBLIC_URL`)
- Ручной тест: `installer/tunnel-testing.cmd`

### 1.5 Конфиг `.env`

```
ALBUM_LINK_SECRET=
SITE_BASE_URL=https://klon008.github.io/princtascdwk
CLO_TOKEN=               # обязателен для автозапуска clo
# CLO_EXE_PATH=          # опц.; default tools/clo/clo.exe
CLO_PUBLIC_URL=          # опц., только тесты без clo
```

### 1.6 Админка OBS (фаза D)

- CRUD бустеров / тиражей на `8765`
- promo JPG → `obs/assets/boosters/`

---

## Часть 2 — Сайт (`princtascdwk`)

| Файл | Назначение |
|------|------------|
| `src/lib/apiCodec.ts` | decrypt `api` param |
| `src/lib/albumApi.ts` | fetchAlbum + типы |
| `src/lib/cardCatalog.ts` | slug → portrait, story |

**App.tsx режимы:** landing / loading / album / offline / unauthorized

**CI:** `VITE_ALBUM_LINK_SECRET` из GH secret (без `VITE_API_BASE_URL`).

---

## Часть 3 — Тесты (`botmsc2`)

- smoke_test.py: token, draw, dup refund, API 401/200
- E2E: бот + clo → `!альбом` → grid

---

## Порядок задач

### Фаза A — фундамент бота
- [x] `m008_cards` + seed 27 карт
- [x] `draws.py`: открытие, дубли, floor refund
- [x] `album_token.py`: `k` + `api` encode
- [x] `album_server.py` + `GET /api/v1/album` на `18770`
- [x] `handler.py`: `!бустер`, `!альбом`

### Фаза B — CLO
- [x] `clo_tunnel.py` + lifecycle в `app.py`
- [x] `.env.example` + README_DEV

### Фаза C — фронт
- [x] `apiCodec.ts` + `albumApi.ts` + `cardCatalog.ts`
- [x] Рефакторинг `App.tsx`
- [x] GH Actions secret (`VITE_ALBUM_LINK_SECRET`)

### Фаза D — админка + полировка
- [x] Админка бустеров/тиражей
- [x] promo JPG upload → `obs/assets/boosters/`
- [x] smoke_test cards API
- [ ] E2E через botmsc2 + реальный clo.exe

### E2E (botmsc2 + clo)

1. `botmsc2\install.cmd` → `start.cmd` (бот)
2. В `.env`: `ALBUM_LINK_SECRET`, убрать `CLO_PUBLIC_URL` для боевого режима
3. `installer\tunnel-testing.cmd` или clo вручную: `clo publish http 18770`
4. `!бустер` / `!альбом` в чате → открыть ссылку на GH Pages
5. Админка: `http://127.0.0.1:8765/admin.html` → вкладка «Карты»

---

## Не в MVP

- P2P обмен, pity, план B (`?c=`), VPS 24×7, порт 8080
