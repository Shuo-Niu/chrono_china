[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

Set-Location $ProjectRoot
& $VenvPython -m chronochina.cli phase1-1
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.1 generation failed. Review data/qa/phase1_1_generation.json."
}

Write-Host "Phase 1.1 active slices and 60-case display QA generated."
