[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

Set-Location $ProjectRoot
& $VenvPython -m chronochina.cli phase1-3-1c-explore
if ($LASTEXITCODE -ne 0) {
    throw "Phase 1.3.1c Explore index generation failed."
}

Write-Host "Phase 1.3.1c compact viewport index generated."
