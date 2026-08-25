# Data redistribution policy

## Public repository boundary

The public ChronoChina repository distributes source code, tests, build
configuration, and project-authored documentation under Apache-2.0. It does
not distribute third-party historical records or map data.

The following paths are intentionally ignored:

```text
data/raw/
data/intermediate/
data/processed/
data/qa/
artifacts/
```

Directory placeholders, `data/README.md`, and the specifically reviewed
project-authored artifacts are versioned:

- `data/metadata/historical_layer_coverage.json`, containing aggregate coverage
  semantics and counts;
- the three exact Qing institution-note draft, source-review, and published
  JSON files listed by `scripts/release_audit.ps1`, containing original
  explanatory prose, citations, review decisions, and matching rules.

These files contain no CHGIS/TGAZ source rows. No other file below `data/` is
approved by these exceptions.

## Files that must not be committed

- downloaded CSV, ZIP, RAR, Shapefile, MapInfo, SQLite, GeoJSON, or API cache;
- normalized or compact indexes containing historical names, coordinates,
  IDs, dates, or parent relationships;
- processed Web datasets and detail-card payloads;
- record-level parity, conflict, coordinate, or unclassified-type reports;
- screenshots or recordings containing third-party map/data content unless a
  separate publication review approves them;
- account credentials, API tokens, temporary signed URLs, or local paths.

## Aggregated findings

Small, project-authored aggregate counts may be described in documentation
after a rights review. Publishing an aggregate does not authorize publishing
the source rows used to calculate it. Record-level samples are treated as data
and remain local by default.

The reviewed coverage metadata is the sole aggregate-data exception. The
institution-note files are project-authored content rather than aggregate
historical data. Publishing either class does not relax the record-level ban
above.

## Contributor responsibility

Before proposing a new source, document:

1. the institution and official entry point;
2. actual API/download access;
3. account, token, or application requirements;
4. record format, time and spatial coverage, and feature taxonomy;
5. research, public-app, commercial, redistribution, and attribution terms;
6. how identity, conflicting assertions, and provenance will be preserved.

When terms conflict or are unclear, apply the stricter interpretation and do
not commit the data.
