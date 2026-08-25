[CmdletBinding()]
param(
    [string]$BuildDate = "20260823",
    [ValidateRange(0, 10)]
    [int]$MaxZoom = 9
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolRoot = Join-Path $ProjectRoot "data\intermediate\offline-map-tools"
$ReferenceRoot = Join-Path $ProjectRoot "data\processed\reference"
$QaRoot = Join-Path $ProjectRoot "data\qa"
$ArchivePath = Join-Path $ReferenceRoot "china_z$MaxZoom.pmtiles"
$ArchiveUrl = "https://build.protomaps.com/$BuildDate.pmtiles"
$Bbox = "72,17,136,55"
$PmtilesVersion = "1.31.2"
$PmtilesZip = Join-Path $ToolRoot "go-pmtiles-$PmtilesVersion.zip"
$PmtilesExe = Join-Path $ToolRoot "pmtiles.exe"
$AssetsCommit = "028c18f713baecad011301ff7a69acc39bcc2ae7"
$AssetsZip = Join-Path $ToolRoot "basemaps-assets-$AssetsCommit.zip"
$AssetsExtract = Join-Path $ToolRoot "basemaps-assets-$AssetsCommit"

$ResolvedProject = [IO.Path]::GetFullPath($ProjectRoot)
$ResolvedReference = [IO.Path]::GetFullPath($ReferenceRoot)
if (-not $ResolvedReference.StartsWith((Join-Path $ResolvedProject "data\processed\reference"), [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write reference data outside the project data directory."
}

function Assert-ChildPath {
    param([string]$Path, [string]$Parent, [string]$Description)
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    $ResolvedParent = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $ResolvedPath.StartsWith($ResolvedParent, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove $Description outside $ResolvedParent"
    }
}

Assert-ChildPath $AssetsExtract $ToolRoot "the extracted asset cache"

New-Item -ItemType Directory -Force -Path $ToolRoot, $ReferenceRoot, $QaRoot | Out-Null

if (-not (Test-Path $PmtilesExe -PathType Leaf)) {
    if (-not (Test-Path $PmtilesZip -PathType Leaf)) {
        Invoke-WebRequest -UseBasicParsing `
            "https://github.com/protomaps/go-pmtiles/releases/download/v$PmtilesVersion/go-pmtiles_$($PmtilesVersion)_Windows_x86_64.zip" `
            -OutFile $PmtilesZip
    }
    Expand-Archive -LiteralPath $PmtilesZip -DestinationPath $ToolRoot -Force
}

$ArchiveTemp = "$ArchivePath.partial"
if (Test-Path $ArchiveTemp -PathType Leaf) {
    Remove-Item -Force -LiteralPath $ArchiveTemp
}
& $PmtilesExe extract $ArchiveUrl $ArchiveTemp --bbox=$Bbox --maxzoom=$MaxZoom --download-threads=8
if ($LASTEXITCODE -ne 0) { throw "PMTiles regional extract failed." }
& $PmtilesExe verify $ArchiveTemp
if ($LASTEXITCODE -ne 0) { throw "PMTiles archive verification failed." }
Move-Item -Force -LiteralPath $ArchiveTemp -Destination $ArchivePath

if (-not (Test-Path $AssetsZip -PathType Leaf)) {
    Invoke-WebRequest -UseBasicParsing `
        "https://github.com/protomaps/basemaps-assets/archive/$AssetsCommit.zip" `
        -OutFile $AssetsZip
}
if (Test-Path $AssetsExtract) {
    Remove-Item -Recurse -Force -LiteralPath $AssetsExtract
}
Expand-Archive -LiteralPath $AssetsZip -DestinationPath $ToolRoot -Force
$AssetsSource = $AssetsExtract
$AssetsDestination = Join-Path $ReferenceRoot "assets"
Assert-ChildPath $AssetsDestination $ReferenceRoot "the packaged asset directory"
if (Test-Path $AssetsDestination) {
    Remove-Item -Recurse -Force -LiteralPath $AssetsDestination
}
New-Item -ItemType Directory -Force -Path `
    (Join-Path $AssetsDestination "fonts"), `
    (Join-Path $AssetsDestination "sprites\v4") | Out-Null
Copy-Item -Recurse -LiteralPath (Join-Path $AssetsSource "fonts\Noto Sans Regular") `
    -Destination (Join-Path $AssetsDestination "fonts")
Copy-Item -Recurse -LiteralPath (Join-Path $AssetsSource "fonts\Noto Sans Medium") `
    -Destination (Join-Path $AssetsDestination "fonts")
Copy-Item -LiteralPath (Join-Path $AssetsSource "fonts\OFL.txt") `
    -Destination (Join-Path $AssetsDestination "fonts\OFL.txt")
Copy-Item -Path (Join-Path $AssetsSource "sprites\v4\light*") `
    -Destination (Join-Path $AssetsDestination "sprites\v4")

$ArchiveFile = Get-Item -LiteralPath $ArchivePath
$AssetFiles = Get-ChildItem -LiteralPath $AssetsDestination -Recurse -File
$Metadata = [ordered]@{
    schema_version = "1.0"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    source = [ordered]@{
        provider = "Protomaps Basemap"
        upstream_url = $ArchiveUrl
        upstream_build_date = $BuildDate
        upstream_tileset_version = "4.15.2"
        assets_commit = $AssetsCommit
        derived_from = "OpenStreetMap and Natural Earth"
        license = "ODbL Produced Work; OpenStreetMap attribution required"
    }
    extract = [ordered]@{
        bbox = @(72, 17, 136, 55)
        minzoom = 0
        maxzoom = $MaxZoom
        size_bytes = $ArchiveFile.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
        path = "data/processed/reference/$($ArchiveFile.Name)"
    }
    assets = [ordered]@{
        file_count = $AssetFiles.Count
        size_bytes = ($AssetFiles | Measure-Object Length -Sum).Sum
        fonts_license = "SIL Open Font License"
        sprites_origin = "Protomaps basemaps-assets"
    }
}
$Metadata | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 `
    -LiteralPath (Join-Path $QaRoot "offline_basemap_manifest.json")

Write-Host "Offline basemap ready: $ArchivePath ($([math]::Round($ArchiveFile.Length / 1MB, 1)) MiB)"
Write-Host "The archive and assets are local generated data and remain excluded from Git."
