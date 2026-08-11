[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

Set-Location $ProjectRoot
& $VenvPython -m chronochina.qa.phase1_2_1
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.2.1 geographic plausibility QA failed."
}

Write-Host "Phase 1.2.1 five-anchor geographic plausibility QA generated."
