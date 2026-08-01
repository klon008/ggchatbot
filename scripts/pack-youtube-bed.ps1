# Pack extensions/youtube-bed into CRX via Chrome --pack-extension.
# Output: dist/youtube-bed.crx
# Key:   extensions/youtube-bed.pem (stable extension id; do not commit)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$ExtDir = Join-Path $Root "extensions\youtube-bed"
$KeyPath = Join-Path $Root "extensions\youtube-bed.pem"
$DistDir = Join-Path $Root "dist"
$OutCrx = Join-Path $DistDir "youtube-bed.crx"

if (-not (Test-Path -LiteralPath $ExtDir)) {
    throw "Extension folder not found: $ExtDir"
}

$pf = [Environment]::GetFolderPath("ProgramFiles")
$pf86 = ${env:ProgramFiles(x86)}
$la = $env:LOCALAPPDATA

$ChromeCandidates = @(
    (Join-Path $pf "Google\Chrome\Application\chrome.exe"),
    (Join-Path $pf86 "Google\Chrome\Application\chrome.exe"),
    (Join-Path $la "Google\Chrome\Application\chrome.exe"),
    (Join-Path $pf86 "Microsoft\Edge\Application\msedge.exe"),
    (Join-Path $pf "Microsoft\Edge\Application\msedge.exe")
)
$Chrome = $ChromeCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $Chrome) {
    throw "Chrome/Edge not found. Install Chrome or set path manually."
}

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$PackedCrx = Join-Path $Root "extensions\youtube-bed.crx"
$PackedPem = Join-Path $Root "extensions\youtube-bed.pem"

if (Test-Path -LiteralPath $PackedCrx) {
    Remove-Item -Force -LiteralPath $PackedCrx
}

$packArgs = @("--pack-extension=$ExtDir")
if (Test-Path -LiteralPath $KeyPath) {
    $packArgs += "--pack-extension-key=$KeyPath"
    Write-Host "Using existing key: $KeyPath"
}
else {
    Write-Host "No key yet - Chrome will create extensions\youtube-bed.pem"
}

Write-Host "Packing with: $Chrome"
$proc = Start-Process -FilePath $Chrome -ArgumentList $packArgs -PassThru -Wait

if (-not (Test-Path -LiteralPath $PackedCrx)) {
    throw "Pack failed: $PackedCrx not created (exit $($proc.ExitCode)). Close Chrome and retry."
}

if ((Test-Path -LiteralPath $PackedPem) -and ($PackedPem -ne $KeyPath)) {
    Move-Item -Force -LiteralPath $PackedPem -Destination $KeyPath
}
if (-not (Test-Path -LiteralPath $KeyPath) -and (Test-Path -LiteralPath $PackedPem)) {
    Move-Item -Force -LiteralPath $PackedPem -Destination $KeyPath
}

Move-Item -Force -LiteralPath $PackedCrx -Destination $OutCrx

Write-Host "OK: $OutCrx"
if (Test-Path -LiteralPath $KeyPath) {
    Write-Host "Key: $KeyPath (keep private; same key = same extension id on rebuild)"
}
Write-Host ""
Write-Host "Install: chrome://extensions -> Developer mode -> drag the .crx,"
Write-Host "or use Load unpacked on extensions\youtube-bed (more reliable on modern Chrome)."
