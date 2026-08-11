$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Project virtual environment is missing. Run scripts/bootstrap.ps1 first."
}

Push-Location $ProjectRoot
try {
    & $Python -m chronochina.temporal_context
    if ($LASTEXITCODE -ne 0) { throw "Phase 1.3 temporal-context generation failed." }
}
finally {
    Pop-Location
}
