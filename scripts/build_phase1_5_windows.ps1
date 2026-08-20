[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WebRoot = Join-Path $ProjectRoot "web"
$ReleaseRoot = Join-Path $ProjectRoot "artifacts\phase1_5\windows"
$ManifestPath = Join-Path $ProjectRoot "data\qa\phase1_5_package_manifest.json"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython -PathType Leaf)) {
    throw "Missing project .venv. Run scripts/bootstrap.ps1 first."
}

$ResolvedProject = [IO.Path]::GetFullPath($ProjectRoot)
$ResolvedRelease = [IO.Path]::GetFullPath($ReleaseRoot)
if (-not $ResolvedRelease.StartsWith((Join-Path $ResolvedProject "artifacts\phase1_5"), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean release output outside artifacts/phase1_5."
}
if (Test-Path $ResolvedRelease) {
    Remove-Item -Recurse -Force -LiteralPath $ResolvedRelease
}

Push-Location $WebRoot
try {
    npm.cmd run pack:windows
    if ($LASTEXITCODE -ne 0) { throw "Windows packaging failed." }
}
finally {
    Pop-Location
}

Copy-Item -LiteralPath (Join-Path $WebRoot "electron\README_FIRST.txt") -Destination $ReleaseRoot
Get-ChildItem -LiteralPath $ReleaseRoot -File -Filter "*.yml" | Remove-Item -Force

& node `
    (Join-Path $WebRoot "electron\verify-package.cjs") `
    (Join-Path $ReleaseRoot "win-unpacked\resources\app.asar")
if ($LASTEXITCODE -ne 0) { throw "app.asar allowlist validation failed." }

$ChecksumFiles = Get-ChildItem -LiteralPath $ReleaseRoot -File | Where-Object {
    $_.Extension -eq ".exe"
} | Sort-Object Name
$ChecksumLines = foreach ($File in $ChecksumFiles) {
    $Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $File.FullName).Hash.ToLowerInvariant()
    "$Hash  $($File.Name)"
}
Set-Content -LiteralPath (Join-Path $ReleaseRoot "SHA256SUMS.txt") -Value $ChecksumLines -Encoding utf8

& $VenvPython -X utf8 -m chronochina.qa.phase1_5_package `
    $ResolvedRelease `
    (Join-Path $WebRoot "dist") `
    $ManifestPath
if ($LASTEXITCODE -ne 0) { throw "Package manifest validation failed." }

Write-Host "Phase 1.5 Windows artifacts created at $ReleaseRoot"
Write-Warning "Distribution remains blocked pending historical-data redistribution confirmation."
