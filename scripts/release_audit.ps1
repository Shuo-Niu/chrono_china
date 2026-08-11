[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$RequiredFiles = @(
    "LICENSE",
    "NOTICE",
    "README.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/data_sources.md",
    "docs/data_redistribution_policy.md"
)

$Failures = [System.Collections.Generic.List[string]]::new()
foreach ($Path in $RequiredFiles) {
    if (-not (Test-Path (Join-Path $ProjectRoot $Path))) {
        $Failures.Add("Missing required public-release file: $Path")
    }
}

$SafeProjectRoot = $ProjectRoot.Replace("\", "/")
$Tracked = @(git -c "safe.directory=$SafeProjectRoot" ls-files)
if ($LASTEXITCODE -ne 0) {
    throw "git ls-files failed."
}

$AllowedDataFiles = @(
    "data/README.md",
    "data/raw/.gitkeep",
    "data/intermediate/.gitkeep",
    "data/processed/.gitkeep",
    "data/qa/.gitkeep"
)

foreach ($Path in $Tracked) {
    $Normalized = $Path.Replace("\", "/")

    if ($Normalized -match "^(artifacts|\.codex-remote-attachments)/") {
        $Failures.Add("Local evidence is tracked: $Normalized")
    }

    if ($Normalized -match "^data/" -and $AllowedDataFiles -notcontains $Normalized) {
        $Failures.Add("Generated or third-party data is tracked: $Normalized")
    }

    if ($Normalized -match "^docs/(phase.*\.md|implementation_baseline\.md|data/|design/|usability/|.*\.pdf)$") {
        $Failures.Add("Internal or source-controlled release-excluded document is tracked: $Normalized")
    }

    $FullPath = Join-Path $ProjectRoot $Path
    if ((Test-Path $FullPath -PathType Leaf) -and (Get-Item $FullPath).Length -gt 5MB) {
        $Failures.Add("Tracked file exceeds 5 MiB review threshold: $Normalized")
    }
}

$TextFiles = $Tracked | Where-Object {
    $_ -ne "scripts/release_audit.ps1" -and (
        $_ -match "\.(md|txt|py|toml|json|ya?ml|tsx?|css|html|ps1|gitignore|gitattributes)$" -or
        $_ -in @("LICENSE", "NOTICE")
    )
}
$LocalPathPattern = "C:\\Users\\|D:\\VibeCoding\\|/Users/[^/]+/|/home/[^/]+/"
$SecretPattern = '(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*[''"]?[A-Za-z0-9_\-]{12,}'

foreach ($Path in $TextFiles) {
    $FullPath = Join-Path $ProjectRoot $Path
    if (-not (Test-Path $FullPath -PathType Leaf)) {
        continue
    }
    $Content = Get-Content -Raw -LiteralPath $FullPath -ErrorAction SilentlyContinue
    if ($null -eq $Content) {
        continue
    }
    if ($Content -match $LocalPathPattern) {
        $Failures.Add("Possible local absolute path in tracked file: $Path")
    }
    if ($Content -match $SecretPattern) {
        $Failures.Add("Possible credential value in tracked file: $Path")
    }
}

if ($Failures.Count -gt 0) {
    $Failures | ForEach-Object { Write-Error $_ }
    throw "Public release audit failed with $($Failures.Count) issue(s)."
}

Write-Host "Public release audit passed for $($Tracked.Count) tracked files."
