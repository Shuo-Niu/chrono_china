[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. Run scripts/bootstrap.ps1 first."
}

Set-Location $ProjectRoot

$DataDependentTests = @(
    "pipeline/tests/test_coverage_metadata.py",
    "pipeline/tests/test_phase1_3_1.py",
    "pipeline/tests/test_phase1_3_1a.py",
    "pipeline/tests/test_phase1_3_1b.py",
    "pipeline/tests/test_phase1_3_1c.py",
    "pipeline/tests/test_phase1_4.py",
    "pipeline/tests/test_temporal_context.py"
)

$PytestArgs = @("-m", "pytest")
foreach ($TestPath in $DataDependentTests) {
    $PytestArgs += @("--ignore", $TestPath)
}

& $VenvPython @PytestArgs
if ($LASTEXITCODE -ne 0) {
    throw "Public Python tests failed."
}

Push-Location (Join-Path $ProjectRoot "web")
try {
    npm.cmd run test:public
    if ($LASTEXITCODE -ne 0) {
        throw "Public Web tests failed."
    }

    npm.cmd run test:desktop
    if ($LASTEXITCODE -ne 0) {
        throw "Public desktop packaging tests failed."
    }

    $PreviousPublicBuild = $env:CHRONOCHINA_PUBLIC_BUILD
    try {
        $env:CHRONOCHINA_PUBLIC_BUILD = "1"
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) {
            throw "Production build failed."
        }
    }
    finally {
        if ($null -eq $PreviousPublicBuild) {
            Remove-Item Env:CHRONOCHINA_PUBLIC_BUILD -ErrorAction SilentlyContinue
        }
        else {
            $env:CHRONOCHINA_PUBLIC_BUILD = $PreviousPublicBuild
        }
    }
}
finally {
    Pop-Location
}

Write-Host "ChronoChina public test suite passed."
