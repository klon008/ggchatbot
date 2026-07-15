# Series Pack Importer

UI (PySide6): импорт ZIP из `series-pack` в бот + фронтенд.

**Не пишет SQL вручную** — генерирует миграцию `m0XX_series_{id}.py` и регистрирует её.
Опционально запускает `scripts/migrate_db.py`.

## Запуск

```bat
run.cmd
```

## Поля

1. Bot root — `E:\programs\OBS\botmsc`
2. Frontend root — `E:\Work\dartvalkkiprincess\princtascdwk`
3. Выбор ZIP → импорт

## Что меняется

| Место | Действие |
|-------|----------|
| Frontend `src/imports` | webp карт + svg рубашки |
| `cardDetails.json` | stories |
| `cardCatalog.ts` / `cardBacks.ts` / `seriesMeta.ts` | каталог, рубашка, серия |
| Bot `obs/assets/cards` | копии артов |
| `bot/db/migrations` | новая миграция + `__init__.py` |

После успеха: **push фронта на GH Pages**, в админке активировать тираж (`queued`).
