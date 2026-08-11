# ChronoChina

[English](README.md) | [简体中文](README.zh-CN.md)

ChronoChina is an open-source research prototype for exploring Chinese historical geography over time. It transforms provenance-preserving TGAZ/CHGIS records into exact-year point maps rendered with MapLibre, while keeping spatial proximity separate from historical lineage.

> Current status: the product and interaction work before Phase 1.4 is frozen. This repository publishes software, tests, and the data pipeline. It does **not** bundle third-party historical datasets or locally generated map datasets.

## What it does

- Queries historical places by exact year in the current viewport.
- Lets users explicitly control historical display families instead of changing them automatically with zoom.
- Switches between Point + Label and Point Only display modes.
- Shows co-located records, provenance, validity periods, and basic details.
- Switches modern reference basemaps without making the historical layer depend on them.
- Downloads, normalizes, validates, and builds Web data through a reproducible Python pipeline.

## Historical-data semantics

- `nearby != same entity`: proximity does not prove identity, succession, or renaming.
- `entity identity != coordinate`: one entity may move; one coordinate may contain several entities.
- Equal names are not automatically merged, and different names are not automatically split.
- Historical Lineage requires explicit evidence; nearest-neighbor logic never creates lineage.
- Missing data does not mean that a place or change did not exist historically.
- Validity periods use closed intervals, and the CE/BCE system has no year zero.
- A historical time slice is never represented as continuous time-series coverage.

## Stack and repository layout

- Python 3.11+: acquisition, normalization, querying, enrichment, and QA.
- React, TypeScript, Vite, and MapLibre GL JS: browser map.
- pytest, Vitest, and Playwright: automated verification.

```text
pipeline/   Python package and tests
web/        Web application
scripts/    Windows PowerShell entry points
data/       Local third-party/generated data (ignored by Git)
docs/       Public engineering and data-governance documentation
```

## Start from a clean checkout

Prerequisites: Git, Windows PowerShell, Python 3.11+, and Node.js `^20.19.0` or `>=22.12.0`.

```powershell
git clone https://github.com/Shuo-Niu/chrono_china.git
Set-Location chrono_china
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

The script creates a project-local `.venv/`, installs Python dependencies from `pyproject.toml`, and runs `npm.cmd ci` using `web/package-lock.json`. It does not install project packages into the system Python environment.

## Acquire and build real data

Read [Data Sources](docs/data_sources.md) and the [Data Redistribution Policy](docs/data_redistribution_policy.md) first. These commands access third-party services, whose current terms remain independently applicable.

```powershell
# Phase 0: real-source acquisition and Gate verification
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase0.ps1

# Web datasets
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1_1.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_phase1_3_1c.ps1
```

The pipeline writes source files to `data/raw/`, normalized data to `data/intermediate/`, Web datasets to `data/processed/`, and QA evidence to `data/qa/`. Generated contents in those directories are excluded from Git. See [data/README.md](data/README.md).

## Run the Web app

After generating `data/processed/`:

```powershell
Set-Location web
npm.cmd run dev
```

The terminal prints the local URL, normally `http://localhost:5173/`. There is no root-level `package.json`; run npm commands inside `web/`.

## Tests

Public, data-independent release tests:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test_public.ps1
```

After generating the complete authorized local dataset, run the full suite and E2E tests:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -E2E
```

## Data rights and commercial use

Open-source code does not make upstream data open data. The project-authored code and documentation are Apache-2.0 and may be used commercially under that license. The principal data sources have separate conditions:

| Source | Commercial use | Redistribution/public hosting |
|---|---|---|
| CHGIS/TGAZ historical content | **Not cleared.** Published CHGIS terms restrict use to non-commercial academic/educational purposes; commercial use requires a separate agreement. | Bulk or Internet redistribution requires written permission. Do not commit raw, normalized, processed, cached, or record-level QA data. |
| GeoNames | Allowed under CC BY 4.0. | Allowed with attribution, a license link, and change notices where applicable. |
| OpenStreetMap/OpenMapTiles/OpenFreeMap | Commercial use is supported. | ODbL, attribution, share-alike obligations for derivative databases, and hosted-service terms still apply. |
| CHGIS V6 and other research candidates | Not cleared for this product. | Conflicting or source-specific terms require a separate rights review and often permission. |

Accordingly, the repository can be open source, but a public or commercial deployment containing CHGIS/TGAZ historical records is **not legally cleared by this repository**. Obtain written permission or replace the historical dataset with a commercially compatible source before commercial launch. This is an engineering rights assessment, not legal advice.

See [Third-Party Notices](THIRD_PARTY_NOTICES.md), [Data Sources](docs/data_sources.md), and the [Data Redistribution Policy](docs/data_redistribution_policy.md).

## Known data limitations

- The current canonical source is the TGAZ/CHGIS 2016 snapshot; CHGIS V6 has not been migrated.
- Town/settlement data primarily comes from the 1820 and 1911 time slices, not continuous coverage.
- Early high-level administrative coverage is uneven.
- Data for 1912–1949 has not been integrated.
- The current version has no historical administrative polygons, dynasty territories, or automatic Historical Lineage.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md). Data changes must preserve provenance, retrieval time, license information, and source identifiers. Mock historical records may not be used to fill coverage gaps.

## License

Project-authored software and documentation are licensed under the [Apache License 2.0](LICENSE). Third-party data, hosted tiles, API responses, and generated datasets are not relicensed by this repository.
