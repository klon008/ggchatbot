@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [series-pack] Creating venv...
  py -3 -m venv .venv
  if errorlevel 1 (
    python -m venv .venv
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\pip.exe" install -r requirements.txt
)

".venv\Scripts\python.exe" -m series_pack
endlocal
