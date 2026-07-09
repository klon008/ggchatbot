#Requires -Version 5.1
<#
.SYNOPSIS
    Первичная установка ggchatbot: git clone, Python, venv, зависимости.
.DESCRIPTION
    Запускайте install.cmd из распакованного архива установщика.
    Репозиторий клонируется в подпапку ggchatbot\ рядом со скриптами.
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/klon008/ggchatbot.git"
$CloneDirName = "ggchatbot"
$MinPythonMajor = 3
$MinPythonMinor = 10

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host ">>> $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "[OK] $Text" -ForegroundColor Green
}

function Write-Warn([string]$Text) {
    Write-Host "[!] $Text" -ForegroundColor Yellow
}

function Write-Err([string]$Text) {
    Write-Host "[ОШИБКА] $Text" -ForegroundColor Red
}

function Pause-Script {
    if ($Host.Name -eq "ConsoleHost") {
        Read-Host "Нажмите Enter для выхода"
    }
}

function Test-GitInstalled {
    return $null -ne (Get-Command git -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    $machine = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Ensure-Git {
    if (Test-GitInstalled) {
        Write-Ok "Git найден: $(git --version)"
        return
    }

    Write-Warn "Git не найден в PATH."
    $answer = Read-Host "Установить Git for Windows? (y/n)"
    if ($answer -notmatch '^[yYдД]') {
        Write-Err "Без Git установка невозможна."
        Write-Host @"

Скачайте Git вручную и перезапустите этот скрипт:
  https://git-scm.com/download/win

При установке оставьте опцию "Git from the command line and also from 3rd-party software".
"@
        Pause-Script
        exit 1
    }

    Write-Step "Установка Git..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements
        Refresh-Path
    }
    else {
        Write-Warn "winget недоступен - откроется страница загрузки Git."
        Start-Process "https://git-scm.com/download/win"
        Write-Host @"

1. Установите Git for Windows (настройки по умолчанию подойдут).
2. Закройте это окно.
3. Откройте новое окно и снова запустите install.cmd.
"@
        Pause-Script
        exit 1
    }

    if (-not (Test-GitInstalled)) {
        Write-Err "Git установлен, но не виден в PATH."
        Write-Host "Перезапустите окно и запустите install.cmd ещё раз."
        Pause-Script
        exit 1
    }

    Write-Ok "Git установлен: $(git --version)"
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

function Test-OnlyInstallerPresent([string]$Path) {
    $allowed = @(
        "install.ps1", "install.cmd",
        "update.ps1", "update.cmd",
        "start.cmd",
        "check-updates.ps1",
        "migrate.cmd",
        "ИНСТРУКЦИЯ.txt",
        $CloneDirName
    )
    $entries = Get-ChildItem -LiteralPath $Path -Force |
        Where-Object { $_.Name -notin @(".", "..") }

    foreach ($entry in $entries) {
        if ($entry.Name -notin $allowed) {
            return $false
        }
    }
    return $true
}

function Resolve-ProjectRoot {
    $launcherDir = $PSScriptRoot

    $existing = Resolve-ProjectDir $launcherDir
    if ($null -ne $existing) {
        if ($existing -eq $launcherDir) {
            Write-Ok "Проект уже на месте: $launcherDir"
        }
        else {
            Write-Ok "Проект найден в: $existing"
        }
        return $existing
    }

    if (Test-OnlyInstallerPresent $launcherDir) {
        Write-Step "Клонируем репозиторий в $CloneDirName\ ..."
        $clonePath = Join-Path $launcherDir $CloneDirName
        if (Test-Path $clonePath) {
            Write-Err "Папка '$CloneDirName' уже существует, но проект в ней не найден."
            Write-Host "Удалите '$clonePath' и запустите install.cmd снова."
            Pause-Script
            exit 1
        }

        git clone $RepoUrl $clonePath
        if (-not (Test-RepoRoot $clonePath)) {
            Write-Err "Клонирование завершилось, но структура репозитория не найдена."
            Pause-Script
            exit 1
        }

        Write-Ok "Репозиторий склонирован в: $clonePath"
        return $clonePath
    }

    Write-Err "Не удалось определить, как установить бота в этой папке."
    Write-Host @"

Ожидается папка с файлами установщика (install.cmd, start.cmd, …).
Скачайте архив с GitHub Releases, распакуйте и запустите install.cmd из неё.
"@
    Pause-Script
    exit 1
}

function Get-PythonCommand {
    $candidates = @(
        @{ Cmd = "py"; Args = @("-3") },
        @{ Cmd = "python"; Args = @() },
        @{ Cmd = "python3"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Cmd -ErrorAction SilentlyContinue)) {
            continue
        }

        try {
            $versionOutput = & $candidate.Cmd @($candidate.Args + @("--version")) 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0 -and -not $versionOutput.Trim()) {
                continue
            }

            if ($versionOutput -notmatch 'Python (\d+)\.(\d+)(?:\.(\d+))?') {
                continue
            }

            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            $micro = if ($Matches[3]) { [int]$Matches[3] } else { 0 }

            return @{
                Command = $candidate.Cmd
                Args    = $candidate.Args
                Major   = $major
                Minor   = $minor
                Micro   = $micro
                Version = ("{0}.{1}.{2}" -f $major, $minor, $micro)
            }
        }
        catch {
            continue
        }
    }

    return $null
}

function Show-PythonInstallHelp {
    $minVersion = "$MinPythonMajor.$MinPythonMinor"
    Write-Host @"

Как исправить:

1. Установите Python $minVersion или новее:
   https://www.python.org/downloads/

2. При установке обязательно отметьте галочку:
   Add python.exe to PATH

3. Закройте это окно, откройте новое.

4. Снова запустите install.cmd

Если не помогло - напишите разработчику.
"@
}

function Test-PythonVersion {
    Write-Step "Проверка Python..."

    $python = Get-PythonCommand
    if ($null -eq $python) {
        Write-Err "Python не найден в PATH."
        Show-PythonInstallHelp
        Pause-Script
        exit 1
    }

    Write-Ok "Найден Python $($python.Version) ($($python.Command))"

    if ($python.Major -lt $MinPythonMajor -or
        ($python.Major -eq $MinPythonMajor -and $python.Minor -lt $MinPythonMinor)) {
        Write-Err "Требуется Python $MinPythonMajor.$MinPythonMinor или новее, найден $($python.Version)."
        Show-PythonInstallHelp
        Pause-Script
        exit 1
    }

    return $python
}

function Invoke-Python([hashtable]$Python, [string[]]$ScriptArgs) {
    & $Python.Command @($Python.Args + $ScriptArgs)
    if ($LASTEXITCODE -ne 0) {
        throw ("Команда завершилась с кодом {0}: {1} {2}" -f $LASTEXITCODE, $Python.Command, ($ScriptArgs -join " "))
    }
}

function Test-RequirementsFile([string]$ProjectRoot) {
    Write-Step "Проверка requirements.txt..."

    $requirementsPath = Join-Path $ProjectRoot "requirements.txt"
    if (-not (Test-Path $requirementsPath)) {
        Write-Err "Файл requirements.txt не найден в $ProjectRoot"
        Pause-Script
        exit 1
    }

    $lines = Get-Content $requirementsPath | Where-Object {
        $_ -and -not ($_.Trim().StartsWith("#"))
    }

    if ($lines.Count -eq 0) {
        Write-Err "requirements.txt пуст."
        Pause-Script
        exit 1
    }

    Write-Ok "requirements.txt найден ($($lines.Count) зависимостей)"
    return $requirementsPath
}

function Show-PipInstallHelp {
    Write-Host @"

Как исправить ошибку установки зависимостей:

1. Проверьте интернет.
2. Запустите install.cmd ещё раз.
3. Если ошибка повторяется - скопируйте текст ошибки и отправьте разработчику.
"@
}

function Install-VirtualEnvironment([string]$ProjectRoot, [hashtable]$Python) {
    Write-Step "Виртуальное окружение и зависимости..."

    Set-Location $ProjectRoot
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

    if (-not (Test-Path $venvPython)) {
        Write-Host "Создаём .venv ..."
        Invoke-Python $Python @("-m", "venv", ".venv")
        Write-Ok "Виртуальное окружение создано"
    }
    else {
        Write-Ok "Виртуальное окружение уже есть"
    }

    Write-Host "Обновляем pip..."
    & $venvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Не удалось обновить pip."
        Show-PipInstallHelp
        Pause-Script
        exit 1
    }

    Write-Host "Устанавливаем зависимости из requirements.txt..."
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Не удалось установить зависимости из requirements.txt."
        Show-PipInstallHelp
        Pause-Script
        exit 1
    }

    Write-Host "Проверяем установленные пакеты..."
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "pip check обнаружил проблемы (см. вывод выше)."
    }
    else {
        Write-Ok "Все зависимости установлены"
    }

    return $venvPython
}

function Ensure-SettingsFile([string]$ProjectRoot, [string]$RelativeDir) {
    $settingsPath = Join-Path $ProjectRoot (Join-Path $RelativeDir "settings.py")
    $examplePath = Join-Path $ProjectRoot (Join-Path $RelativeDir "settings.example.py")

    if (Test-Path $settingsPath) {
        Write-Ok "$RelativeDir\settings.py уже существует (не перезаписываем)"
        return
    }

    if (Test-Path $examplePath) {
        Copy-Item $examplePath $settingsPath
        Write-Ok "Создан $RelativeDir\settings.py — настройте баланс под свой канал"
    }
    else {
        Write-Warn "$RelativeDir\settings.example.py не найден — создайте settings.py вручную"
    }
}

function Ensure-EnvFile([string]$ProjectRoot) {
    $dataDir = Join-Path $ProjectRoot "data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir | Out-Null
        Write-Ok "Создана папка data\"
    }
    else {
        Write-Ok "Папка data\ уже есть"
    }

    $envPath = Join-Path $ProjectRoot ".env"
    $examplePath = Join-Path $ProjectRoot ".env.example"

    if (Test-Path $envPath) {
        Write-Ok ".env уже существует (не перезаписываем)"
        return
    }

    if (Test-Path $examplePath) {
        Copy-Item $examplePath $envPath
        Write-Ok "Создан .env - попросите разработчика заполнить настройки GoodGame"
    }
    else {
        Write-Warn ".env.example не найден - создайте .env вручную"
    }
}

function Show-FinishMessage([string]$LauncherDir, [string]$ProjectRoot) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host " Установка завершена" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Папка с кнопками:  $LauncherDir"
    if ($ProjectRoot -ne $LauncherDir) {
        Write-Host "Файлы проекта:     $ProjectRoot"
    }
    Write-Host ""
    Write-Host "Дальше:"
    Write-Host "  1. Напишите разработчику - он настроит .env"
    Write-Host "  2. Перед стримом: start.cmd"
    Write-Host "  3. Обновление кода: update.cmd"
    Write-Host "  4. Новая версия установщика - архив с GitHub Releases"
    Write-Host ""
    Write-Host "Подробная инструкция: ИНСТРУКЦИЯ.txt"
    Write-Host ""
}

try {
    Write-Host "=== ggchatbot - установка ===" -ForegroundColor Cyan

    $launcherDir = $PSScriptRoot

    Ensure-Git
    $python = Test-PythonVersion
    $projectRoot = Resolve-ProjectRoot
    Set-Location $projectRoot

    $null = Test-RequirementsFile $projectRoot
    $null = Install-VirtualEnvironment $projectRoot $python
    Ensure-EnvFile $projectRoot
    Ensure-SettingsFile $projectRoot "bot\princess"
    Ensure-SettingsFile $projectRoot "bot\song_request"
    Show-FinishMessage $launcherDir $projectRoot
}
catch {
    Write-Err $_.Exception.Message
    if ($_.ScriptStackTrace) {
        Write-Host $_.ScriptStackTrace
    }
    Pause-Script
    exit 1
}

Pause-Script
