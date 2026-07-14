#Requires -Version 5.1
<#
.SYNOPSIS
    Синхронизация артов карт и лора (cardDetails.json) с репозитория сайта.

.DESCRIPTION
    Источник по умолчанию выводится из SITE_BASE_URL в .env:

      https://USER.github.io/REPO/  →  https://github.com/USER/REPO
      арты:   src/imports/*.webp (+ card-back*.svg)
      лор:    src/app/cardDetails.json

    Кэш репозитория: data/card-assets-repo (sparse checkout).
    Копии:
      obs/assets/cards/          — webp + svg рубашек
      data/cards/cardDetails.json — описания (только чтение в админке)

.PARAMETER ProjectDir
    Корень бота (где main.py и .env). По умолчанию — родитель scripts\.

.PARAMETER SrcImports
    Локальный путь к папке imports (минуя GitHub). Пример:
    E:\Work\dartvalkkiprincess\princtascdwk\src\imports
    Рядом ожидается ..\app\cardDetails.json (или задайте -SrcCardDetails).

.PARAMETER SrcCardDetails
    Локальный путь к cardDetails.json (опционально вместе с -SrcImports).

.PARAMETER EnvFile
    Путь к .env (по умолчанию ProjectDir\.env).
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = "",
    [string]$SrcImports = "",
    [string]$SrcCardDetails = "",
    [string]$EnvFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

function Read-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    $prefix = "$Key="
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#")) { continue }
        if ($t.StartsWith($prefix)) {
            return $t.Substring($prefix.Length).Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function Convert-SiteBaseToGitHubRepo {
    param([Parameter(Mandatory = $true)][string]$SiteBaseUrl)

    $u = $SiteBaseUrl.Trim().TrimEnd("/")
    if ($u -match '^https?://([^.]+)\.github\.io/([^/]+)') {
        $user = $Matches[1]
        $repo = $Matches[2]
        return "https://github.com/$user/$repo.git"
    }
    if ($u -match '^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$') {
        return "https://github.com/$($Matches[1])/$($Matches[2]).git"
    }
    return $null
}

function Ensure-Git {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git не найден в PATH"
    }
}

function Copy-CardDetailsJson {
    param(
        [Parameter(Mandatory = $true)][string]$SourceFile,
        [Parameter(Mandatory = $true)][string]$DestFile
    )
    if (-not (Test-Path -LiteralPath $SourceFile)) {
        Write-Warn "cardDetails.json не найден: $SourceFile"
        return $false
    }
    $destDir = Split-Path -Parent $DestFile
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item -LiteralPath $SourceFile -Destination $DestFile -Force
    Write-Ok "Описания: $DestFile"
    return $true
}

function Resolve-CardDetailsBesideImports {
    param([Parameter(Mandatory = $true)][string]$ImportsDir)
    # src/imports → src/app/cardDetails.json
    $appDir = Join-Path (Split-Path -Parent $ImportsDir) "app"
    return (Join-Path $appDir "cardDetails.json")
}

function Sync-FromLocalImports {
    param(
        [Parameter(Mandatory = $true)][string]$ImportsDir,
        [Parameter(Mandatory = $true)][string]$DestDir
    )
    if (-not (Test-Path -LiteralPath $ImportsDir)) {
        throw "Папка imports не найдена: $ImportsDir"
    }
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
    $webp = @(Get-ChildItem -LiteralPath $ImportsDir -Filter "*.webp" -File)
    $backs = @(Get-ChildItem -LiteralPath $ImportsDir -Filter "card-back*.svg" -File)
    if ($webp.Count -eq 0) {
        throw "В $ImportsDir нет *.webp"
    }
    Copy-Item -LiteralPath ($webp | ForEach-Object { $_.FullName }) -Destination $DestDir -Force
    if ($backs.Count -gt 0) {
        Copy-Item -LiteralPath ($backs | ForEach-Object { $_.FullName }) -Destination $DestDir -Force
    }
    return ($webp.Count + $backs.Count)
}

function Ensure-SparseCheckoutFiles {
    param([Parameter(Mandatory = $true)][string]$CacheDir)
    $sparseFile = Join-Path $CacheDir ".git\info\sparse-checkout"
    $wanted = @(
        "src/imports/",
        "src/app/cardDetails.json"
    )
    $content = ($wanted -join "`n") + "`n"
    if (-not (Test-Path -LiteralPath $sparseFile)) {
        Set-Content -LiteralPath $sparseFile -Value $content -Encoding ASCII -NoNewline
        return $true
    }
    $existing = Get-Content -LiteralPath $sparseFile -Raw -ErrorAction SilentlyContinue
    if ($null -eq $existing) { $existing = "" }
    $needRewrite = $false
    foreach ($line in $wanted) {
        if ($existing -notmatch [regex]::Escape($line)) {
            $needRewrite = $true
            break
        }
    }
    if ($needRewrite) {
        Set-Content -LiteralPath $sparseFile -Value $content -Encoding ASCII -NoNewline
        return $true
    }
    return $false
}

function Sync-FromGitHub {
    param(
        [Parameter(Mandatory = $true)][string]$RepoUrl,
        [Parameter(Mandatory = $true)][string]$CacheDir,
        [Parameter(Mandatory = $true)][string]$DestDir,
        [Parameter(Mandatory = $true)][string]$DetailsDest
    )

    Ensure-Git
    New-Item -ItemType Directory -Force -Path (Split-Path $CacheDir -Parent) | Out-Null

    if (-not (Test-Path (Join-Path $CacheDir ".git"))) {
        Write-Step "Клонируем репозиторий карт (sparse: src/imports + cardDetails.json)"
        if (Test-Path -LiteralPath $CacheDir) {
            Remove-Item -LiteralPath $CacheDir -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
        Push-Location $CacheDir
        try {
            git init | Out-Null
            git remote add origin $RepoUrl
            git config core.sparseCheckout true
            [void](Ensure-SparseCheckoutFiles -CacheDir $CacheDir)
            git pull --depth 1 origin main
            if ($LASTEXITCODE -ne 0) {
                git pull --depth 1 origin master
            }
            if ($LASTEXITCODE -ne 0) {
                throw "git pull $RepoUrl не удался"
            }
        }
        finally {
            Pop-Location
        }
    }
    else {
        $sparseChanged = Ensure-SparseCheckoutFiles -CacheDir $CacheDir
        Write-Step "git pull кэша карт"
        Push-Location $CacheDir
        try {
            if ($sparseChanged) {
                git read-tree -mu HEAD 2>$null
                git checkout HEAD -- . 2>$null
            }
            git pull --ff-only
            if ($LASTEXITCODE -ne 0) {
                throw "git pull в $CacheDir не удался"
            }
        }
        finally {
            Pop-Location
        }
    }

    $imports = Join-Path $CacheDir "src\imports"
    $count = Sync-FromLocalImports -ImportsDir $imports -DestDir $DestDir
    $detailsSrc = Join-Path $CacheDir "src\app\cardDetails.json"
    [void](Copy-CardDetailsJson -SourceFile $detailsSrc -DestFile $DetailsDest)
    return $count
}

# --- main ---
if (-not $ProjectDir) {
    $ProjectDir = Split-Path $PSScriptRoot -Parent
}
$ProjectDir = (Resolve-Path -LiteralPath $ProjectDir).Path

if (-not $EnvFile) {
    $EnvFile = Join-Path $ProjectDir ".env"
}

$dest = Join-Path $ProjectDir "obs\assets\cards"
$detailsDest = Join-Path $ProjectDir "data\cards\cardDetails.json"
$cache = Join-Path $ProjectDir "data\card-assets-repo"

Write-Step "Синхронизация артов и описаний карт"

$count = 0
if ($SrcImports) {
    Write-Host "Источник (локально): $SrcImports"
    $count = Sync-FromLocalImports -ImportsDir $SrcImports -DestDir $dest
    $detailsSrc = $SrcCardDetails
    if (-not $detailsSrc) {
        $detailsSrc = Resolve-CardDetailsBesideImports -ImportsDir $SrcImports
    }
    [void](Copy-CardDetailsJson -SourceFile $detailsSrc -DestFile $detailsDest)
}
else {
    $siteBase = Read-DotEnvValue -Path $EnvFile -Key "SITE_BASE_URL"
    if (-not $siteBase) {
        throw "SITE_BASE_URL не задан в $EnvFile (нужен для URL репозитория карт)"
    }
    $repoUrl = Convert-SiteBaseToGitHubRepo -SiteBaseUrl $siteBase
    if (-not $repoUrl) {
        throw "Не удалось вывести GitHub-репо из SITE_BASE_URL='$siteBase'. Ожидается https://USER.github.io/REPO/"
    }
    if ($repoUrl -match 'github\.com/([^/]+)/([^/.]+)') {
        $treeHint = "https://github.com/$($Matches[1])/$($Matches[2])/tree/main/src/imports"
        $jsonHint = "https://github.com/$($Matches[1])/$($Matches[2])/blob/main/src/app/cardDetails.json"
    }
    else {
        $treeHint = ""
        $jsonHint = ""
    }
    Write-Host "SITE_BASE_URL: $siteBase"
    Write-Host "GitHub:        $repoUrl"
    if ($treeHint) {
        Write-Host "Imports:       $treeHint"
        Write-Host "Stories:       $jsonHint"
    }
    $count = Sync-FromGitHub -RepoUrl $repoUrl -CacheDir $cache -DestDir $dest -DetailsDest $detailsDest
}

Write-Ok "Скопировано $count файл(ов) артов → $dest"
