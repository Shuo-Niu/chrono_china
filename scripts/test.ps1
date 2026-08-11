[CmdletBinding()]
param(
    [switch]$E2E
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

Set-Location $ProjectRoot
& $VenvPython -m pytest
if ($LASTEXITCODE -ne 0) {
    throw "Python tests failed."
}

Push-Location (Join-Path $ProjectRoot "web")
try {
    npm.cmd test
    if ($LASTEXITCODE -ne 0) {
        throw "Web unit tests failed."
    }

    npm.cmd run build
    if ($LASTEXITCODE -ne 0) {
        throw "Web production build failed."
    }

    if ($E2E) {
        npm.cmd run e2e
        if ($LASTEXITCODE -ne 0) {
            throw "Playwright E2E tests failed."
        }
    }
}
finally {
    Pop-Location
}

Write-Host "ChronoChina verification complete."
