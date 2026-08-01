# YouTube Bed — расширение Chrome / Edge

Пауза фонового YouTube / YouTube Music на время заказов `!зм` / `!sr` бота.
Между заказами музыка стримера продолжается (если вкладка активирована).

Без активации вкладки поведение бота не меняется: заказы играют, между ними тишина.

## Установка (load unpacked) — надёжный способ

1. Chrome: `chrome://extensions` → «Режим разработчика» → «Загрузить распакованное расширение» → эта папка.
2. Edge: `edge://extensions` → то же самое.
3. ПКМ по иконке расширения → «Параметры» → Host / Port как в `.env` бота (`OBS_WS_HOST`, `OBS_WS_PORT`). По умолчанию `127.0.0.1` / `8765`.
4. Откройте YouTube или YouTube Music, клик по иконке расширения — badge **ON**. Повторный клик снимает bed.

## Сборка `.crx`

```powershell
.\scripts\pack-youtube-bed.ps1
```

Результат: `dist\youtube-bed.crx`. Ключ подписи: `extensions\youtube-bed.pem` (в git не попадает; сохраняйте локально, иначе при пересборке сменится id расширения).

На современном Chrome установка `.crx` вне Web Store часто блокируется — тогда используйте load unpacked выше.

## Как работает

```
Вкладка YouTube ← content.js (WebSocket) ← ws://HOST:PORT/ws ← бот
OBS player.html  ← тот же /ws
```

1. Content script шлёт `{status:"ready", overlay:"bed"}` (обязательно `overlay`, иначе бот примет клиент за OBS-плеер).
2. На `play` или `queue_state.playing=true` — `video.pause()`, флаг `pausedByBot`.
3. На `queue_state.playing=false` — `video.play()` **только если** паузу ставило расширение (ручная пауза стримера не форсится).

## OBS

Звук браузера и Browser Source плеера заказов лучше развести (Application Audio Capture браузера vs источник плеера), чтобы не дублировать захват.
