@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
cd /d "%ROOT%"
if exist "ggchatbot\main.py" cd /d "%ROOT%ggchatbot"
title ggchatbot
if not exist ".venv\Scripts\python.exe" (
    echo Сначала запустите install.cmd
    pause
    exit /b 1
)
if not exist ".env" (
    echo Файл .env не найден. Запустите install.cmd или напишите разработчику.
    pause
    exit /b 1
)
set "CHECK_PS1=%ROOT%check-updates.ps1"
if exist "check-updates.ps1" set "CHECK_PS1=%CD%\check-updates.ps1"
if exist "%CHECK_PS1%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%CHECK_PS1%"
)
set "UPDATE_MSG=%TEMP%\ggchatbot-update.msg"
if exist "%UPDATE_MSG%" (
    echo.
    type "%UPDATE_MSG%"
    del "%UPDATE_MSG%" >nul 2>&1
    echo.
)
echo Запуск бота... Закройте это окно, чтобы остановить бота.
.\.venv\Scripts\python.exe main.py
echo.
echo Бот остановлен.
pause
