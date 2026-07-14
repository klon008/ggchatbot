# TODO

Рулетка и скачки реализованы (см. `README_DEV.md`). Мини-игра №3 — ожидает ТЗ.

---

## Коллекционные карты — лор (описания)

### Разделение данных

| Что | Где | Как менять |
|-----|-----|------------|
| Тиражи, цены, пул, active/pause, лимиты | SQLite бота | Админка OBS (быстро) |
| Кому выпала карта, дата | SQLite (`user_cards`) | runtime |
| Имя, rarity, slug, серия | SQLite (`cards`) | миграции / админ-каталог |
| Портреты webp, рубашки svg | репо сайта `src/imports` | git → `update.cmd` → `obs/assets/cards` |
| **Описания (story)** | репо сайта `src/app/cardDetails.json` | редко: правки в git (разработчик) → Pages + `update.cmd` |

Описания **не** пишутся в БД и **не** редактируются в админке.
`save_cards.cmd` / push с машины стримера — **не делаем**.

### Поток файлов

```
princtascdwk/src/app/cardDetails.json   ← источник правды (ключи = slug)
        │
        │  update.cmd → scripts/sync-card-assets.ps1
        │  (sparse git: src/imports + src/app/cardDetails.json)
        ▼
bot/data/cards/cardDetails.json         ← зеркало (data/ в .gitignore)
        │
        ▼
Admin GET /api/cards/catalog            ← поле story, только чтение
Site CardModal                          ← тот же json бандлится Vite
```

### Workflow правок лора (MVP)

1. Стример формулирует текст / скидывает правки разработчику.
2. Разработчик правит `cardDetails.json`, commit + push в репо сайта.
3. После деплоя Pages стример запускает `update.cmd` (подтянется json + арты).
4. Админка показывает обновлённые описания.

Ключи только **slug** (`cinderella`, `queen-elsa`, …), не русские имена.

Подробнее для разработчика: `README_DEV_CARDS.md` (бот и сайт).

---

## Мини-игра №3

> Спецификация ожидается. Отдельный модуль `bot/<название>/`.

- [ ] Утвердить ТЗ и имя модуля
- [ ] Реализовать
