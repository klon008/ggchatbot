@echo off
chcp 65001 >nul
set "ROOT=%~dp0.."
cd /d "%ROOT%"
set "CLO=%CD%\tools\clo\clo.exe"
if not exist "%CLO%" (
    echo clo.exe не найден: %CLO%
    pause
    exit /b 1
)
echo === tunnel-testing.cmd ===
echo Ручной тест CLO без бота. Для продакшена не нужен — бот сам поднимает clo.
echo Album API должен уже слушать 127.0.0.1:18770 (или тест упадёт).
echo.
set "CLO_TOKEN="
if exist "%CD%\.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (`findstr /b /i /c:"CLO_TOKEN=" "%CD%\.env"`) do set "CLO_TOKEN=%%B"
)
if defined CLO_TOKEN if not "%CLO_TOKEN%"=="" (
    echo Записываю CLO_TOKEN через clo set token ...
    "%CLO%" set token %CLO_TOKEN%
) else (
    echo WARNING: CLO_TOKEN пуст в .env — использую уже сохранённый token clo.
)
echo.
echo Запуск: clo publish http 18770
echo Закройте окно, чтобы остановить туннель.
"%CLO%" publish http 18770
pause
