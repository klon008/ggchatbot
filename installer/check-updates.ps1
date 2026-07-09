#Requires -Version 5.1
<#
.SYNOPSIS
    Проверка: есть ли на GitHub новые коммиты (без git pull).
    При наличии обновлений пишет UTF-8 сообщение во временный файл;
    start.cmd выводит его через TYPE (корректная кириллица в cmd).
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$CloneDirName = "ggchatbot"
$UpdateMsgFile = Join-Path $env:TEMP "ggchatbot-update.msg"

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

function Get-UpdateWord([int]$Count) {
    if ($Count % 10 -eq 1 -and $Count % 100 -ne 11) {
        return "обновление"
    }
    if ($Count % 10 -in 2, 3, 4 -and $Count % 100 -notin 12, 13, 14) {
        return "обновления"
    }
    return "обновлений"
}

function Write-UpdateNotice([int]$Count) {
    $word = Get-UpdateWord $Count
    $esc = [char]27
    # ANSI red для cmd (VT включён в start.cmd перед TYPE).
    $line = "${esc}[91mНайдены обновления ($Count $word), запустите update.cmd${esc}[0m"
    $utf8Bom = New-Object System.Text.UTF8Encoding $true
    [System.IO.File]::WriteAllText($UpdateMsgFile, $line + [Environment]::NewLine, $utf8Bom)
}

function Clear-UpdateNotice() {
    if (Test-Path -LiteralPath $UpdateMsgFile) {
        Remove-Item -LiteralPath $UpdateMsgFile -Force -ErrorAction SilentlyContinue
    }
}

Clear-UpdateNotice

$projectDir = Resolve-ProjectDir $PSScriptRoot
if ($null -eq $projectDir) {
    exit 0
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    exit 0
}

if (-not (Test-Path (Join-Path $projectDir ".git"))) {
    exit 0
}

Push-Location $projectDir
try {
    $null = git fetch origin --quiet 2>&1
    if ($LASTEXITCODE -ne 0) {
        exit 0
    }

    $branch = (git rev-parse --abbrev-ref HEAD 2>$null).Trim()
    if (-not $branch) {
        exit 0
    }

    $upstream = "origin/$branch"
    $null = git rev-parse --verify $upstream 2>$null
    if ($LASTEXITCODE -ne 0) {
        exit 0
    }

    $behind = (git rev-list --count "HEAD..$upstream" 2>$null).Trim()
    if ($behind -match '^\d+$' -and [int]$behind -gt 0) {
        Write-UpdateNotice ([int]$behind)
    }

    exit 0
}
finally {
    Pop-Location
}
