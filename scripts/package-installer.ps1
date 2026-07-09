#Requires -Version 5.1
<#
.SYNOPSIS
    Build installer zip for GitHub Releases.
.DESCRIPTION
    Packs installer\ contents into dist\ggchatbot-installer.zip (flat root, no installer\ prefix).
#>
[CmdletBinding()]
param(
    [string]$OutDir = "dist",
    [string]$ZipName = "ggchatbot-installer.zip"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path $PSScriptRoot -Parent
$installerDir = Join-Path $repoRoot "installer"

if (-not (Test-Path (Join-Path $installerDir "install.cmd"))) {
    Write-Error "installer folder not found: $installerDir"
}

$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("ggchatbot-installer-" + [guid]::NewGuid().ToString("n"))
$null = New-Item -ItemType Directory -Path $staging -Force

try {
    Get-ChildItem -LiteralPath $installerDir -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $staging -Force
    }

    $outPath = Join-Path $repoRoot $OutDir
    $null = New-Item -ItemType Directory -Path $outPath -Force
    $zipPath = Join-Path $outPath $ZipName

    if (Test-Path $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

    Write-Host "[OK] $zipPath" -ForegroundColor Green
    Write-Host "Upload this file to GitHub Releases." -ForegroundColor Cyan
}
finally {
    if (Test-Path $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}
