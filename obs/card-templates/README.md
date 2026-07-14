# Card rarity templates (OBS)

Пустые HTML/SVG-рамки карточек по редкостям - **без React**.

Скопировано из `princtascdwk/card-templates` для анимации прокрутки бустеров в OBS.

Локальный путь: `obs/card-templates/`  
HTTP (когда бот запущен): `http://127.0.0.1:8765/card-templates/preview.html`

## Файлы

| Файл | Назначение |
|------|------------|
| `common.svg` … `secretRare.svg` | пустой фрейм редкости |
| `card-fx.css` | анимации holo / mythic |
| `fill-card.js` | хелпер подстановки имени/арта |
| `preview.html` | визуальный просмотр всех рамок |

## Использование

```html
<link rel="stylesheet" href="/card-templates/card-fx.css" />
<div id="card" style="width:280px"></div>
<script type="module">
  import { mountCardTemplate } from "/card-templates/fill-card.js";
  await mountCardTemplate(document.getElementById("card"), "rare", {
    name: "Elsa",
    portraitUrl: "/assets/cards/elsa.webp",
  });
</script>
```

`mountCardTemplate` грузит SVG относительно URL модуля (`/card-templates/{rarity}.svg`).

Слоты в SVG:
- `[data-slot="name"]` - текст имени
- `[data-slot="portrait"]` - `<image href="…">`

Арты портретов - из `obs/assets/cards/{slug}.webp`.
