@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
cd /d "%ROOT%"
if exist "ggchatbot\main.py" cd /d "%ROOT%ggchatbot"
title ggchatbot - migrate JSON to SQLite

if not exist ".venv\Scripts\python.exe" (
    echo Сначала запустите install.cmd
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Миграция JSON -^> SQLite (data\bot.db)
echo ========================================
echo.
echo 1. Положите в папку data\ файлы со старого бота:
echo      princess_points.json
echo      steal_chance_and_count.json
echo      daily_bonus.json
echo      queue.json
echo.
echo 2. Скрипт сделает backup data\ и создаст bot.db
echo 3. Успешные JSON будут переименованы в .json.bak
echo.

if exist "data\*.json" (
    echo Найдены JSON в data\:
    dir /b data\*.json
) else (
    echo [!] В data\ нет .json файлов - будет создана пустая база.
)
echo.

set /p CONFIRM=Продолжить миграцию? (y/n):
if /i not "%CONFIRM%"=="y" (
    echo Отменено.
    pause
    exit /b 0
)

echo.
.\.venv\Scripts\python.exe scripts\migrate_json_to_sqlite.py
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo [ОШИБКА] Миграция завершилась с кодом %RC%
) else (
    echo [OK] Готово. Можно запускать start.cmd
)
pause
exit /b %RC%
