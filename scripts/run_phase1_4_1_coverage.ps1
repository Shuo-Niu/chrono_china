$ProjectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -m chronochina.cli phase1-4-1-coverage
if ($LASTEXITCODE -ne 0) { throw "Phase 1.4.1 coverage metadata generation failed." }
