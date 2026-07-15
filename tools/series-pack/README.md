# Series Pack UI

Десктопный wizard (Python / PySide6) для сборки **ZIP-пака новой серии карт**.

**Не пишет в `bot.db`.** Только собирает архив; миграции создаёшь отдельно из json.

## Запуск

```bat
run.cmd
```

Первый запуск создаст `.venv` и поставит зависимости.

## Шаги

1. Серия — `series_id`, имя, `card_back_id` (`card-back-*`), SVG-рубашка (превью), порядок  
2. Карты — DnD / Ctrl+V / файлы → webp 310×330, id / имя / редкость / описание  
3. Бустер — id, название, promo URL  
4. Тираж — цена, N карт, лимит, веса редкостей (% live) → ZIP  

После успеха: путь к архиву + ссылка https://t.me/klon_008

## Формат ZIP

```
MANIFEST.json
series.json          # series + booster + draw + cards meta
stories.json         # slug → lore
backs/{card_back_id}.svg
cards/{card_id}.webp
```

`pack_version: 1`
