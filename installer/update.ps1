#Requires -Version 5.1
<#
.SYNOPSIS
    Обновление ggchatbot: git pull, sync лаунчеров, зависимости Python.

.ORDER КРИТИЧЕСКИ ВАЖЕН — не менять последовательность и не вставлять шаги между этапами 1–3:

    1. git pull          — сначала подтянуть код из репозитория (в т.ч. ggchatbot\installer\).
    2. sync лаунчеров    — сравнить installer\ с корневой папкой установщика, скопировать отличия.
    3. перезапуск себя   — только если изменились update.ps1 или update.cmd (см. -AfterLauncherSync).
    4. pip / settings    — всё остальное только после этапов 1–3.

    Почему нельзя ничего вставлять между pull и sync:
    - sync берёт файлы из ggchatbot\installer\ ПОСЛЕ pull; иначе копируется устаревшая версия.
    - если изменился update.ps1, текущий процесс выполняет СТАРУЮ логику; нужен один перезапуск
      уже обновлённого скрипта из корня (флаг -AfterLauncherSync пропускает повторный sync).

    Лаунчеры в корне (update.cmd, start.cmd, …) правит только разработчик в репозитории.
    Стример запускает update.cmd — скрипт сам подтягивает свежие копии из installer\.
.PARAMETER AfterLauncherSync
    Внутренний флаг второго прохода после sync и перезапуска. Не передавать вручную.
#>
[CmdletBinding()]
param(
    [switch]$AfterLauncherSync
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/klon008/ggchatbot.git"
$CloneDirName = "ggchatbot"

# Файлы установщика: канон в ggchatbot\installer\, копии — в корне у стримера.
$LauncherFileNames = @(
    "install.ps1", "install.cmd",
    "update.ps1", "update.cmd",
    "start.cmd",
    "check-updates.ps1",
    "migrate.cmd",
    "ИНСТРУКЦИЯ.txt"
)

# Имена, при изменении которых нужен перезапуск update.ps1 (остальное — только копирование).
$LauncherRestartNames = @("update.ps1", "update.cmd")

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

function Get-FileSha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-ChangedLauncherFiles {
    param(
        [string]$InstallerDir,
        [string]$LauncherDir,
        [string[]]$Names
    )

    $changed = New-Object System.Collections.Generic.List[string]
    foreach ($name in $Names) {
        $src = Join-Path $InstallerDir $name
        if (-not (Test-Path -LiteralPath $src)) {
            continue
        }

        $dst = Join-Path $LauncherDir $name
        $srcHash = Get-FileSha256 $src
        $dstHash = Get-FileSha256 $dst
        if ($srcHash -ne $dstHash) {
            $changed.Add($name)
        }
    }
    return $changed
}

function Sync-LauncherFiles {
    param(
        [string]$InstallerDir,
        [string]$LauncherDir,
        [string[]]$Names
    )

    foreach ($name in $Names) {
        $src = Join-Path $InstallerDir $name
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $LauncherDir $name) -Force
        }
    }
}

function Update-LauncherFromInstaller {
    param(
        [string]$ProjectDir,
        [string]$LauncherDir
    )

    $installerDir = Join-Path $ProjectDir "installer"
    if (-not (Test-Path -LiteralPath $installerDir)) {
        return
    }

    $changed = Get-ChangedLauncherFiles -InstallerDir $installerDir -LauncherDir $LauncherDir -Names $LauncherFileNames
    if ($changed.Count -eq 0) {
        return
    }

    Write-Step "Обновление файлов установщика"
    Sync-LauncherFiles -InstallerDir $installerDir -LauncherDir $LauncherDir -Names $LauncherFileNames
    Write-Ok "Обновлены: $($changed -join ', ')"

    $needsRestart = @($changed | Where-Object { $_ -in $LauncherRestartNames })
    if ($needsRestart.Count -gt 0) {
        Write-Step "Перезапуск update.ps1 (обновилась логика обновления)"
        $restartScript = Join-Path $LauncherDir "update.ps1"
        & $restartScript -AfterLauncherSync
        exit $LASTEXITCODE
    }
}

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

# --- Этап 1: git pull (см. .ORDER в заголовке файла) ---
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

# --- Этапы 2–3: sync лаунчеров и при необходимости перезапуск (только первый проход) ---
if (-not $AfterLauncherSync) {
    Update-LauncherFromInstaller -ProjectDir $projectDir -LauncherDir $launcherDir
}

# --- Этап 4: настройки, зависимости и завершение ---
Ensure-SettingsFile $projectDir "bot\princess"
Ensure-SettingsFile $projectDir "bot\song_request"
Ensure-SettingsFile $projectDir "bot\roulette"
Write-Host ""
Write-Host "Настройки баланса: bot\princess\settings.py, bot\song_request\settings.py, bot\roulette\settings.py" -ForegroundColor Yellow
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

    Write-Step "Миграция базы данных"
    & $venvPython scripts\migrate_db.py
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Миграция bot.db не удалась."
        Write-Host "Закройте окно бота (start.cmd) и запустите update.cmd снова." -ForegroundColor Yellow
        Pause-Script
        exit 1
    }
    Write-Ok "База данных обновлена"
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
