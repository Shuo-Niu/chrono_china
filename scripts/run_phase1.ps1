[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

Set-Location $ProjectRoot
& $VenvPython -m chronochina.cli phase1
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1 data generation failed. Review data/qa/phase1_api_failures.json and phase1_data_generation.json."
}

Write-Host "Phase 1 five-anchor data generated. Run scripts/test.ps1 -E2E to verify the UI."
