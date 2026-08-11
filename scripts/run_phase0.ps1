[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

Set-Location $ProjectRoot

foreach ($Gate in @("g0", "g1", "g2", "g3", "g4", "g5")) {
    & $VenvPython -m chronochina.cli $Gate
    if ($LASTEXITCODE -ne 0) {
        throw "Blocking Phase 0 command '$Gate' failed. See data/qa for evidence."
    }
}

foreach ($Probe in @("g6", "g7")) {
    & $VenvPython -m chronochina.cli $Probe
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Non-blocking probe '$Probe' failed. Review data/qa before proceeding."
    }
}

Write-Host "Phase 0 pipeline finished. Reports are in data/qa/."
