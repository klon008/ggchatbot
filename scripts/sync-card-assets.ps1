#Requires -Version 5.1
<#
.SYNOPSIS
    Синхронизация артов карт и лора (cardDetails.json) с репозитория сайта.

.DESCRIPTION
    Источник по умолчанию:

      CARD_ASSETS_REPO_URL в .env  →  https://github.com/OWNER/REPO.git
      (если пусто — вывод из SITE_BASE_URL:
       https://USER.github.io/REPO/  →  https://github.com/USER/REPO.git)

      Канон проекта: SITE_BASE_URL=https://klon008.github.io/princtascdwk/
      арты:   src/imports/*.webp (+ card-back*.svg)
      лор:    src/app/cardDetails.json

    Кэш репозитория: data/card-assets-repo (sparse checkout).
    Копии артов: obs/assets/cards/
    Лор бот читает прямо из кэша:
      data/card-assets-repo/src/app/cardDetails.json

.PARAMETER ProjectDir
    Корень бота (где main.py и .env). По умолчанию — родитель scripts\.

.PARAMETER SrcImports
    Локальный путь к папке imports (минуя GitHub). Пример:
    E:\Work\dartvalkkiprincess\princtascdwk\src\imports
    Рядом ожидается ..\app\cardDetails.json (или задайте -SrcCardDetails);
    json копируется в data/card-assets-repo/src/app/ (тот же путь, что после git pull).

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

function Normalize-GitHubRepoUrl {
    param([Parameter(Mandatory = $true)][string]$Raw)
    $u = $Raw.Trim().TrimEnd("/")
    if ($u -match '^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$') {
        return "https://github.com/$($Matches[1])/$($Matches[2]).git"
    }
    return $null
}

function Convert-SiteBaseToGitHubRepo {
    param([Parameter(Mandatory = $true)][string]$SiteBaseUrl)

    $u = $SiteBaseUrl.Trim().TrimEnd("/")
    if ($u -match '^https?://([^.]+)\.github\.io/([^/]+)') {
        $user = $Matches[1]
        $repo = $Matches[2]
        return "https://github.com/$user/$repo.git"
    }
    return (Normalize-GitHubRepoUrl -Raw $u)
}

function Resolve-CardAssetsRepoUrl {
    param(
        [Parameter(Mandatory = $true)][string]$EnvFile
    )
    # Явный URL репо (опционально; иначе вывод из SITE_BASE_URL).
    $explicit = Read-DotEnvValue -Path $EnvFile -Key "CARD_ASSETS_REPO_URL"
    if ($explicit) {
        $norm = Normalize-GitHubRepoUrl -Raw $explicit
        if (-not $norm) {
            throw "CARD_ASSETS_REPO_URL='$explicit' — ожидается https://github.com/OWNER/REPO.git"
        }
        return @{ Url = $norm; Source = "CARD_ASSETS_REPO_URL"; SiteBase = "" }
    }
    $siteBase = Read-DotEnvValue -Path $EnvFile -Key "SITE_BASE_URL"
    if (-not $siteBase) {
        throw "Задайте CARD_ASSETS_REPO_URL или SITE_BASE_URL в $EnvFile"
    }
    $derived = Convert-SiteBaseToGitHubRepo -SiteBaseUrl $siteBase
    if (-not $derived) {
        throw "Не удалось вывести GitHub-репо из SITE_BASE_URL='$siteBase'. Задайте CARD_ASSETS_REPO_URL=https://github.com/OWNER/REPO.git"
    }
    return @{ Url = $derived; Source = "SITE_BASE_URL→derived"; SiteBase = $siteBase }
}

function Ensure-Git {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw "Git не найден в PATH"
    }
}

function Copy-CardDetailsIntoCache {
    param(
        [Parameter(Mandatory = $true)][string]$SourceFile,
        [Parameter(Mandatory = $true)][string]$CacheDetailsPath
    )
    if (-not (Test-Path -LiteralPath $SourceFile)) {
        Write-Warn "cardDetails.json не найден: $SourceFile"
        return $false
    }
    $destDir = Split-Path -Parent $CacheDetailsPath
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Copy-Item -LiteralPath $SourceFile -Destination $CacheDetailsPath -Force
    Write-Ok "Описания в кэше: $CacheDetailsPath"
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

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$GitArgs,
        [switch]$Quiet
    )
    # git часто пишет в stderr даже при успехе; при $ErrorActionPreference=Stop
    # PowerShell превращает это в исключение — глушим NativeCommandError.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) {
            & git @GitArgs 1>$null 2>$null
        }
        else {
            & git @GitArgs 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    Write-Host $_.Exception.Message
                }
                else {
                    Write-Host $_
                }
            }
        }
        return $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prev
    }
}

function Resolve-OriginBranch {
    <#
    .SYNOPSIS
        Какая ветка на origin: main или master (без зависимости от upstream local).
    #>
    $code = Invoke-Git -GitArgs @("rev-parse", "--verify", "--quiet", "refs/remotes/origin/main") -Quiet
    if ($code -eq 0) { return "main" }
    $code = Invoke-Git -GitArgs @("rev-parse", "--verify", "--quiet", "refs/remotes/origin/master") -Quiet
    if ($code -eq 0) { return "master" }
    return $null
}

function Pull-CardCache {
    param(
        [Parameter(Mandatory = $true)][string]$CacheDir
    )
    # Всегда: fetch + sync на origin/<branch>. Не полагаемся на upstream
    # (shallow sparse clone после git init часто без tracking → "no tracking information").
    Push-Location $CacheDir
    try {
        $code = Invoke-Git -GitArgs @("fetch", "--depth", "1", "origin")
        if ($code -ne 0) {
            throw "git fetch origin в $CacheDir не удался"
        }
        $branch = Resolve-OriginBranch
        if (-not $branch) {
            $code = Invoke-Git -GitArgs @("fetch", "--depth", "1", "origin", "main")
            if ($code -eq 0) {
                $branch = "main"
            }
            else {
                $code = Invoke-Git -GitArgs @("fetch", "--depth", "1", "origin", "master")
                if ($code -ne 0) {
                    throw "Не найдены ветки origin/main и origin/master в $CacheDir"
                }
                $branch = "master"
            }
        }
        $code = Invoke-Git -GitArgs @("checkout", "-B", $branch, "origin/$branch") -Quiet
        if ($code -ne 0) {
            $code = Invoke-Git -GitArgs @("pull", "--ff-only", "origin", $branch)
            if ($code -ne 0) {
                throw "git pull origin $branch в $CacheDir не удался"
            }
        }
        else {
            [void](Invoke-Git -GitArgs @("branch", "--set-upstream-to=origin/$branch", $branch) -Quiet)
        }
    }
    finally {
        Pop-Location
    }
}

function Sync-FromGitHub {
    param(
        [Parameter(Mandatory = $true)][string]$RepoUrl,
        [Parameter(Mandatory = $true)][string]$CacheDir,
        [Parameter(Mandatory = $true)][string]$DestDir
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
            [void](Invoke-Git -GitArgs @("init") -Quiet)
            [void](Invoke-Git -GitArgs @("remote", "add", "origin", $RepoUrl) -Quiet)
            [void](Invoke-Git -GitArgs @("config", "core.sparseCheckout", "true") -Quiet)
            [void](Ensure-SparseCheckoutFiles -CacheDir $CacheDir)
        }
        finally {
            Pop-Location
        }
        Write-Step "git pull кэша карт (первый раз)"
        Pull-CardCache -CacheDir $CacheDir
    }
    else {
        [void](Ensure-SparseCheckoutFiles -CacheDir $CacheDir)
        # если раньше вывели репо из SITE_BASE_URL неверно — чиним remote
        Push-Location $CacheDir
        try {
            [void](Invoke-Git -GitArgs @("remote", "set-url", "origin", $RepoUrl) -Quiet)
        }
        finally {
            Pop-Location
        }
        Write-Step "git pull кэша карт"
        Pull-CardCache -CacheDir $CacheDir
    }

    $imports = Join-Path $CacheDir "src\imports"
    $count = Sync-FromLocalImports -ImportsDir $imports -DestDir $DestDir
    $detailsInCache = Join-Path $CacheDir "src\app\cardDetails.json"
    if (Test-Path -LiteralPath $detailsInCache) {
        Write-Ok "Описания в кэше: $detailsInCache"
    }
    else {
        Write-Warn "cardDetails.json нет в кэше после pull: $detailsInCache"
    }
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
$cache = Join-Path $ProjectDir "data\card-assets-repo"
$cacheDetails = Join-Path $cache "src\app\cardDetails.json"

Write-Step "Синхронизация артов и описаний карт"

$count = 0
if ($SrcImports) {
    Write-Host "Источник (локально): $SrcImports"
    $count = Sync-FromLocalImports -ImportsDir $SrcImports -DestDir $dest
    $detailsSrc = $SrcCardDetails
    if (-not $detailsSrc) {
        $detailsSrc = Resolve-CardDetailsBesideImports -ImportsDir $SrcImports
    }
    # Тот же путь, что после git pull — бот читает только его
    [void](Copy-CardDetailsIntoCache -SourceFile $detailsSrc -CacheDetailsPath $cacheDetails)
}
else {
    $resolved = Resolve-CardAssetsRepoUrl -EnvFile $EnvFile
    $repoUrl = $resolved.Url
    if ($repoUrl -match 'github\.com/([^/]+)/([^/.]+)') {
        $treeHint = "https://github.com/$($Matches[1])/$($Matches[2])/tree/main/src/imports"
        $jsonHint = "https://github.com/$($Matches[1])/$($Matches[2])/blob/main/src/app/cardDetails.json"
    }
    else {
        $treeHint = ""
        $jsonHint = ""
    }
    if ($resolved.SiteBase) {
        Write-Host "SITE_BASE_URL: $($resolved.SiteBase)"
    }
    Write-Host "Repo source:  $($resolved.Source)"
    Write-Host "GitHub:       $repoUrl"
    if ($treeHint) {
        Write-Host "Imports:      $treeHint"
        Write-Host "Stories:      $jsonHint"
    }
    $count = Sync-FromGitHub -RepoUrl $repoUrl -CacheDir $cache -DestDir $dest
}

Write-Ok "Скопировано $count файл(ов) артов → $dest"
