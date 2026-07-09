#Requires -Version 5.1
<#
.SYNOPSIS
    Обновление ggchatbot: git pull и зависимости Python.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/klon008/ggchatbot.git"
$CloneDirName = "ggchatbot"

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host ">>> $Text" -ForegroundColor Cyan
}

function Write-Err([string]$Text) {
    Write-Host "[ОШИБКА] $Text" -ForegroundColor Red
}

function Write-Ok([string]$Text) {
    Write-Host "[OK] $Text" -ForegroundColor Green
}

function Write-Warn([string]$Text) {
    Write-Host "[!] $Text" -ForegroundColor Yellow
}

function Pause-Script {
    if ($Host.Name -eq "ConsoleHost") {
        Read-Host "Нажмите Enter для выхода"
    }
}

function Test-RepoRoot([string]$Path) {
    return (Test-Path (Join-Path $Path "main.py")) -and
           (Test-Path (Join-Path $Path "requirements.txt")) -and
           (Test-Path (Join-Path $Path "bot"))
}

function Resolve-ProjectDir([string]$LauncherDir) {
    $nested = Join-Path $LauncherDir $CloneDirName
    if (Test-RepoRoot $nested) {
        return $nested
    }
    if (Test-RepoRoot $LauncherDir) {
        return $LauncherDir
    }
    return $null
}

$launcherDir = $PSScriptRoot
$projectDir = Resolve-ProjectDir $launcherDir

if ($null -eq $projectDir) {
    Write-Err "Проект не найден."
    Write-Host @"

Ожидалась папка ggchatbot\ с ботом или файлы проекта в текущей папке.
Сначала запустите install.cmd.
"@
    Pause-Script
    exit 1
}

Set-Location $projectDir
if ($projectDir -ne $launcherDir) {
    Write-Ok "Проект: $projectDir"
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Err "Git не установлен."
    Write-Host @"

Установите Git for Windows:
  https://git-scm.com/download/win

Или запустите install.cmd - он предложит установить Git.
"@
    Pause-Script
    exit 1
}

if (-not (Test-Path (Join-Path $projectDir ".git"))) {
    Write-Err "Папка проекта не является git-репозиторием."
    Write-Host @"

Сначала выполните первичную установку:
  install.cmd

Или вручную:
  git clone $RepoUrl
"@
    Pause-Script
    exit 1
}

Write-Step "git pull"
git pull
if ($LASTEXITCODE -ne 0) {
    Write-Err "git pull завершился с ошибкой."
    Write-Host @"

Возможные причины:
  - нет интернета;
  - конфликт с локальными изменениями файлов;
  - репозиторий на GitHub недоступен.

Напишите разработчику, не меняйте файлы бота вручную.
"@
    Pause-Script
    exit 1
}

Write-Ok "Код обновлён"

function Ensure-SettingsFile([string]$ProjectRoot, [string]$RelativeDir) {
    $settingsPath = Join-Path $ProjectRoot (Join-Path $RelativeDir "settings.py")
    $examplePath = Join-Path $ProjectRoot (Join-Path $RelativeDir "settings.example.py")

    if (Test-Path $settingsPath) {
        return
    }

    if (Test-Path $examplePath) {
        Copy-Item $examplePath $settingsPath
        Write-Warn "Создан $RelativeDir\settings.py из шаблона — проверьте баланс под свой канал"
    }
    else {
        Write-Warn "$RelativeDir\settings.example.py не найден — создайте settings.py вручную"
    }
}

Ensure-SettingsFile $projectDir "bot\princess"
Ensure-SettingsFile $projectDir "bot\song_request"
Write-Host ""
Write-Host "Настройки баланса: bot\princess\settings.py и bot\song_request\settings.py" -ForegroundColor Yellow
Write-Host "сохраняются при обновлении. Сравните с *.example.py, если в репо появились новые параметры." -ForegroundColor Yellow

$venvPython = Join-Path $projectDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Step "Обновление зависимостей Python"
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Не удалось обновить pip - продолжаем."
    }

    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Не удалось установить зависимости."
        Write-Host "Запустите install.cmd или напишите разработчику."
        Pause-Script
        exit 1
    }

    Write-Ok "Зависимости обновлены"
}
else {
    Write-Warn ".venv не найден - запустите install.cmd для полной установки."
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " Обновление завершено" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "1. Закройте окно бота (если оно открыто)" -ForegroundColor Yellow
Write-Host "2. Запустите снова: start.cmd" -ForegroundColor Yellow
Write-Host ""

Pause-Script
