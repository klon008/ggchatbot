# Карточные арты для OBS Admin

Файлы `{slug}.webp` раздаются ботом:

```
http://127.0.0.1:8765/assets/cards/anna.webp
```

В БД: `cards.image_url` = `/assets/cards/anna.webp`.

Источник правды — репозиторий сайта. Из `SITE_BASE_URL` в `.env`:

```
https://USER.github.io/REPO/  →  https://github.com/USER/REPO/tree/main/src/imports
```

Синхронизация:

```powershell
powershell -File scripts\sync-card-assets.ps1
# копирует *.webp и card-back*.svg из src/imports
```
