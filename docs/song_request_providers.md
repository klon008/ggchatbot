# Song-request: провайдеры воспроизведения

Одна очередь, один активный звук. Одновременно YouTube и Яндекс Музыка **не** играют.

## Этап 1 — iframe (отклонён)

Официальный embed `music.yandex.ru/iframe/...` не даёт автоплея и не пробрасывает Plus в OBS Browser Source. Оставлен только как исторический этап.

## Этап 2 — `<audio>` (текущий)

- Бот с `YANDEX_MUSIC_TOKEN` (аккаунт с Plus) скачивает трек через неофициальный API (`yandex-music`).
- Файл в `data/ym_cache/`, раздача `GET /ym/file/{play_token}`.
- OBS: HTML5 `<audio>` + now-playing; `ended` от элемента, watchdog на сервере.
- Токен: двойной клик `tools/yandex_music_token.cmd` → `.env` → `YANDEX_MUSIC_TOKEN=...`
- Заказы без токена отклоняются; YouTube работает отдельно.
- Exclusive: `activeBackend` youtube | yandex.
- Фильтр `content_warning=explicit`: по умолчанию вкл; галочка в админке (Заказы музыки → «Блокировать explicit»).

## Этап 3 — кастомный API / Ynison

Если `<audio>`/API скачивания неустойчивы:

- Ynison (управление приложением ЯМузыки) или другой клиент API.
- Звук из приложения → Desktop Audio в OBS; оверлей now-playing отдельно.
