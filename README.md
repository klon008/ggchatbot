# OBS Song Request Bot (GoodGame)

> Документация для разработчиков: [README_DEV.md](README_DEV.md)

Чат-бот для стриминга: зрители заказывают музыку командой `!sr <ссылка YouTube>`,
бот проверяет ссылку, ведёт очередь и по локальному WebSocket проигрывает видео
в источнике «Браузер» в OBS. Когда трек заканчивается, автоматически играет
следующий.

## Как это работает

```
Зритель ── !sr ──▶ Чат GoodGame ──▶ Python-бот ──(WebSocket)──▶ Плеер в OBS
                                        ▲                              │
                                        └────── ended/error ──────────┘
```

1. **Приём/валидация (Python):** ловит `!sr`, извлекает `videoId` из ссылки,
   кладёт в очередь (с сохранением на диск).
2. **Передача в OBS (WebSocket):** локальный сервер шлёт плееру
   `{"action":"play","videoId":...,"token":...}`.
3. **Воспроизведение (HTML/JS):** страница в OBS через YouTube IFrame API
   играет видео. Длительность (≤ `MAX_DURATION_SEC`) и live-стримы проверяются
   прямо в плеере; невстраиваемые/age-restricted ролики отдают ошибку.
4. **Закольцовка:** по окончании плеер шлёт `{"status":"ended",...}`, бот берёт
   следующий трек. Если очередь пуста — ждёт новых заказов.

## Требования

- Python 3.10+
- OBS с источником «Браузер» (CEF)
- Аккаунт GoodGame для бота (чтобы писать ответы в чат)

## Установка

### Быстрый способ (для клиента)

Подробная инструкция: [installer/ИНСТРУКЦИЯ.txt](installer/ИНСТРУКЦИЯ.txt)

1. Скачайте архив установщика из [GitHub Releases](https://github.com/klon008/ggchatbot/releases).
2. Распакуйте и дважды нажмите **install.cmd**.
3. Напишите разработчику — он настроит `.env`.
4. Перед стримом — **start.cmd**.
5. Обновление кода бота — **update.cmd**.

### Ручная установка (для разработчика)

```powershell
git clone https://github.com/klon008/ggchatbot.git
cd ggchatbot
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
copy bot\princess\settings.example.py bot\princess\settings.py
copy bot\song_request\settings.example.py bot\song_request\settings.py
copy bot\roulette\settings.example.py bot\roulette\settings.py
.\.venv\Scripts\python.exe main.py
```

Сборка zip для Releases:

```powershell
.\scripts\package-installer.ps1
# → dist\ggchatbot-installer.zip
```

## Настройка `.env`

| Переменная | Описание |
|------------|----------|
| `GG_LOGIN`, `GG_PASSWORD` | Логин/пароль аккаунта бота на GoodGame. Нужны, чтобы бот писал ответы в чат (гости — readonly). |
| `GG_USER_ID` | ID бота. Можно оставить пустым — подставится после логина (нужен, чтобы игнорировать собственные сообщения). |
| `GG_CHANNEL_ID` | Числовой ID вашего канала. |
| `OBS_WS_HOST`, `OBS_WS_PORT` | Хост/порт локального сервера (по умолчанию `127.0.0.1:8765`). Один порт и для HTTP-страницы, и для WebSocket. |
| `MAX_QUEUE_SIZE` | Максимум треков в очереди. |
| `MAX_DURATION_SEC` | Лимит длительности трека (проверяется в плеере). |
| `TRACK_WATCHDOG_EXTRA_SEC` | Запас к лимиту для watchdog принудительного перехода. |
| `USER_COOLDOWN_SEC` | Антиспам: пауза между `!sr` одного пользователя (`0` = выкл). |

## Настройка баланса (принцессы, !sr)

Баланс игры (очки за сообщения, кража, дейлики, стоимость `!sr` и т.д.) задаётся
в локальных файлах, которые **не попадают в git** и **сохраняются при `update.cmd`**:

| Файл | Шаблон в репозитории |
|------|----------------------|
| `bot/princess/settings.py` | `bot/princess/settings.example.py` |
| `bot/song_request/settings.py` | `bot/song_request/settings.example.py` |
| `bot/roulette/settings.py` | `bot/roulette/settings.example.py` |

При первой установке (`install.cmd` или ручное копирование) создаётся `settings.py`
из `settings.example.py`. Меняйте только свой `settings.py`.

После обновления кода сравните `*.example.py` с вашим `settings.py` — если в репо
появились новые параметры, перенесите их вручную.

### Как узнать `GG_CHANNEL_ID`

ID канала — числовой идентификатор стрима (не путать с логином/`channel_key`).
Его видно, например, в исходнике страницы канала или через API GoodGame.

## Настройка OBS

1. Добавьте источник **«Браузер»**.
2. В поле **URL** укажите (именно `http://`, НЕ локальный файл):

   ```
   http://127.0.0.1:8765/player.html
   ```

   Для диагностики (тёмная подложка + логи на экране):

   ```
   http://127.0.0.1:8765/player.html?debug=1
   ```

   > Важно: открытие через `file://` даёт **YouTube error 153** — с июля 2025
   > embed нельзя использовать как top-level документ без валидного Referer.
   > Поэтому страницу отдаёт локальный HTTP-сервер бота.
3. Ширина/высота — под вашу сцену (напр. 1280×720).
4. Включите **«Управление звуком через OBS»** (Control audio via OBS).
5. **Снимите** галку «Выключать источник, когда он не отображается»
   (Shutdown source when not visible) — иначе при переключении сцен плеер
   выгрузится и потеряет соединение. Бот переподключится сам, но так надёжнее.

**Прозрачный оверлей:** когда очередь пуста и ничего не играет, источник
«Браузер» полностью прозрачен — на сцене не видно ни чёрного квадрата YouTube,
ни последнего кадра после окончания трека. Видео появляется только на время
воспроизведения заказа.

## Команды чата

| Команда | Кто | Действие |
|---------|-----|----------|
| `!заказ` / `!зм` / `!sr <ссылка>` | все | Заказать трек с YouTube. |
| `!пропуск` / `!skip` | модераторы+ | Пропустить текущий трек. |
| `!очередь` | все | Показать длину очереди и следующие треки. |
| `!играет` / `!сейчас` | все | Показать, что играет сейчас. |
| `!команды` | все | Список публичных команд бота. |

Поддерживаемые форматы ссылок: `youtube.com/watch?v=`, `youtu.be/`,
`youtube.com/shorts/`, `youtube.com/embed/`, `youtube.com/live/`,
`music.youtube.com`, `m.youtube.com`.

## Проверка без чата

Быстрый автотест обвязки (HTTP + WebSocket + цикл очереди, без GoodGame):

```powershell
.\.venv\Scripts\python.exe smoke_test.py
```

Он проверяет раздачу `player.html`/`player.js`, переход `play #1 -> play #2`,
защиту от двойного скипа (устаревший `token` игнорируется) и опустошение очереди.

Проверить сам плеер визуально: запустите `python main.py` и откройте
`http://127.0.0.1:8765/player.html` в обычном браузере — страница прозрачна
(ничего не видно), пока не придёт заказ `!sr`.

## Устранение неполадок

- **Чёрный квадрат / последний кадр на сцене** — обновите `player.html`/`player.js`
  (lazy-init + скрытие в idle). Перезагрузите источник в OBS (ПКМ → Обновить).
- **Чёрный экран / error 153** — открыли `file://` вместо `http://...`. Используйте URL выше.
- **Заказ не играет, в консоли `iframe_api ERR_CONNECTION_RESET`** — YouTube заблокирован
  на ПК стримера. Нужен VPN на весь компьютер (не только браузер). Откройте
  `player.html?debug=1` — на экране будут причина и логи; бот напишет в чат при первой ошибке.
- **Нет звука** — включите «Управление звуком через OBS»; плеер стартует в mute и
  размьючивается после старта (обход autoplay-политики).
- **Видео сразу пропускается** — оно недоступно для встраивания (101/150),
  удалено/приватно (100), длиннее лимита или это live-стрим.
- **Бот молчит в чате** — не заданы `GG_LOGIN`/`GG_PASSWORD` (гость readonly).
- **Очередь не сбрасывается при перезапуске** — она специально хранится в
  `data/queue.json`. Удалите файл, чтобы очистить.

## Дальнейшие улучшения (TODO)

- YouTube Data API: pre-check длительности/18+/стоп-слов **до** добавления
  (заготовка — `bot/song_request/youtube.py`, ключ `YOUTUBE_API_KEY`).
- Чёрный список названий/каналов.
- Донат-приоритет очереди (в GG-сообщениях есть поле `payments`).
- Переход на OAuth2 вместо логина/пароля.

## Структура проекта

```
botmsc/
  installer/              # установщик для клиента (→ zip в Releases)
    install.cmd, start.cmd, update.cmd, …
  main.py                 # точка входа
  config.py               # загрузка .env
  bot/
    app.py                # оркестратор (StreamBot)
    goodgame/             # общий WS-клиент чата GoodGame v2
      client.py
    song_request/         # заказ музыки через YouTube + OBS
      handler.py          # команды !sr / !skip / очередь / watchdog
      queue.py            # очередь + атомарная персистентность
      obs_server.py       # aiohttp: статика player.html/js + WebSocket
      youtube.py          # извлечение/валидация videoId
    princess/             # игровая экономика «принцесс»
      handler.py          # команды !кража / !баллы / …
      storage.py          # JSON в data/
      economy.py
      prison.py
  obs/
    player.html
    player.js             # YouTube IFrame API + WS
  data/
    queue.json            # song-request (в .gitignore)
    princess_points.json  # princess (в .gitignore)
    …
```
