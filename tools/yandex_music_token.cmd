@echo off
setlocal
cd /d "%~dp0\.."

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "tools\yandex_music_token.py"
  exit /b 0
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "tools\yandex_music_token.py"
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "tools\yandex_music_token.py"
  exit /b %ERRORLEVEL%
)

python "tools\yandex_music_token.py"
exit /b %ERRORLEVEL%
