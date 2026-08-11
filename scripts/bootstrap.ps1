[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $VenvPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .venv with the available Python runtime."
    }
}

& $VenvPython -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency installation failed."
}

Push-Location (Join-Path $ProjectRoot "web")
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) {
        throw "Node dependency installation failed."
    }
}
finally {
    Pop-Location
}

Write-Host "ChronoChina bootstrap complete."
