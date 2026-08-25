# ChronoChina Phase 1.4.1 Coverage Semantics Design

## Revision status

This revision replaces the original single-state resolver. It is based on a direct audit of the frozen Phase 1.4 canonical processed index and closes three design errors:

1. `settlement` is a mixed display family, not an alias for raw `村镇` snapshots.
2. The canonical temporal envelope comes from the frozen index, not TGAZ documentation.
3. High-admin zero-count intervals are not promoted to precise source-sparsity claims without source-level evidence.

No production code, metadata artifact, UI, or historical record is changed by this design revision.

## Goal

Make User Mode distinguish source coverage from historical absence without changing any historical source fact. Coverage semantics describe what the current canonical source can support; they never assert that a place or administrative level historically did not exist.

## Scope and constraints

- Keep the current TGAZ/CHGIS 2016 snapshot as the canonical historical source.
- Do not add or migrate data sources, including CHGIS V6.
- Do not modify raw or normalized records, coordinates, IDs, names, feature types, provenance, or `BEG`/`END`.
- Do not hide a real record merely because its display family has limited or mixed coverage.
- Preserve viewport-driven exploration, continuous exact-year navigation, manual layer toggles, co-location rules, marker alignment, basemap behavior, and incremental rendering.
- User Mode shows only exceptional or special source-coverage text. Normal time-series coverage adds no text.
- Developer Mode may show full component-level diagnostics.

## Frozen evidence baseline

The authoritative input for this design is:

- `data/processed/explore/tgaz_compact.json`
- Phase 1.4 frozen SHA-256: `7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf`
- Current SHA-256 recheck: the same value
- Record count: 71,393
- Actual minimum `valid_from`: **-763**
- Actual maximum `valid_to`: **1912**

Therefore, the current frozen canonical envelope is **-763..1912**. This is an observed property of this exact frozen index, not a permanent constant. A future metadata build must recompute the envelope from the frozen canonical records and reject a mismatch; it must not clip records to a documentation range.

The TGAZ API documentation range `-222..1911` is retained only as a provenance note. It is not a validation boundary because the frozen index contains valid records outside it, including `hvd_70930` beginning at -763 and multiple county/prefecture records ending at 1912.

## Settlement-family audit

The current `settlement` display family is defined by exact source taxonomy, not record-name inference. It contains exactly two raw source types:

| Raw source type | Records | Observed periods | Temporal model | Coverage interpretation |
|---|---:|---|---|---|
| `村镇` | 48,690 | 8,659 at 1820..1820; 40,031 at 1911..1911 | Named `TIME_SLICE` component | Real village/town snapshots at 1820 and 1911 only; never extend to adjacent years |
| `亭` | 18 | 17 at 14..22; 1 at 623..959 | Interval-based `TIME_SERIES` component | Real interval records inside those validity periods; source completeness for the broader settlement category is unknown |

There are no other raw types in the current settlement registry. The classification comes from `web/src/display/hierarchy.ts` and `pipeline/chronochina/qa/phase1_3_1f.py`, both frozen in Phase 1.4.

### Required-year interpretation

- **14:** 17 active raw `亭` records, all valid 14..22. They remain visible and are described as interval-based settlement-family records.
- **626:** one active raw `亭` record, `hvd_115201` 杜邮亭, valid 623..959. It remains visible.
- **750:** the same real interval record remains valid and visible.
- **1819:** no settlement-family component in the current source covers this year. Raw 1820 `村镇` records are not backfilled.
- **1820:** 8,659 raw `村镇` snapshot records are eligible only at 1820.
- **1821:** no settlement-family component covers this year. Raw 1820 `村镇` records are not extended.
- **1910:** raw 1911 `村镇` records are not backfilled.
- **1911:** 40,031 raw `村镇` snapshot records are eligible only at 1911.

The UI must never show “该时期暂无资料” at 14, 626, or 750 merely because the raw `村镇` snapshot component is inactive. Family-level records are the union of all enabled, exact-year-valid components.

## High-admin evidence assessment

The current `high_admin` family contains exact raw types `王畿`, `省`, `行省`, and `省级`:

| Raw type | Records | Observed envelope | Single-year records | Interval records |
|---|---:|---|---:|---:|
| `王畿` | 4 | -399..463 | 0 | 4 |
| `省` | 79 | 1220..1911 | 37 | 42 |
| `行省` | 81 | 1234..1381 | 17 | 64 |
| `省级` | 1 | 1911..1911 | 1 | 0 |

These facts prove that the display family mixes interval and single-year records. They do **not** prove completeness for all historical high-level institutions. A one-year validity interval is not automatically a dataset-level snapshot; `TIME_SLICE` requires source-layer evidence, not `BEG == END` alone.

Phase 1.4 provides source-level evidence that CHGIS publishes named province point snapshots for 1820 and 1911 and does not provide an updated province time-series core layer. However, the frozen compact index has no source-layer field that can reliably map every high-admin record to those packages. Consequently:

- the former exact `SPARSE_COVERAGE` intervals 208–458, 464–1219, and 1382–1643 are removed;
- zero yearly `high_admin` counts remain QA observations only;
- the design does not infer source sparsity from those counts;
- historical differences between `王畿`, `行省`, and later `省` are not flattened into a single institutional continuity claim;
- high-admin completeness is conservatively `LIMITED` at family level;
- no exact-year high-admin snapshot badge is shown in User Mode until component provenance can be identified from the canonical source itself.

The evidence for `LIMITED` is source-level and non-numeric: Phase 1.4 confirmed that the available CHGIS province material consists of uneven interval records plus named 1820/1911 snapshots, with no continuous replacement province layer in V6. The evidence does not support precise sparse-period boundaries.

## Revised state model: two orthogonal axes

Coverage and query results are separate. No mutually exclusive priority enum may collapse them.

### Axis A: source coverage assessment

`SourceCoverageAssessment` is structured rather than a single enum:

- `components`: the source components relevant to the display family and current year;
- each component has `raw_types`, `temporal_model`, `supported_periods`, and provenance;
- `temporal_models`: a set containing zero, one, or both of:
  - `TIME_SERIES`
  - `TIME_SLICE`
- `support`:
  - `SUPPORTED`: source-level evidence positively supports the named component and year;
  - `UNSUPPORTED`: no current source component claims coverage for the family and year;
  - `LIMITED`: source-level evidence establishes partial or uneven coverage but not completeness;
  - `UNKNOWN`: available evidence cannot determine coverage completeness.

`temporal_models` is a set because one display family can contain both an interval component and a snapshot component in the same year. `support` describes evidence quality and does not suppress real records.

`SPARSE_COVERAGE` is not emitted in Phase 1.4.1 because no source-backed sparse intervals have been established. It may be added only if later evidence identifies explicit source coverage boundaries; yearly counts alone remain insufficient.

### Axis B: viewport result

`ViewportResult` is independent:

- `HAS_RECORDS`: one or more exact-year-valid, enabled-family records are eligible in the current viewport before label collision.
- `NO_RECORDS`: zero such records are eligible in the current viewport.

This axis describes the current query result only. `NO_RECORDS` never means historical absence.

The diagnostic model also retains:

- global current-year active source count by component and family;
- current viewport eligible count;
- final displayed-unit count after co-location and collision.

These counts explain the display pipeline but do not determine source completeness by themselves.

### Required combinations

The two-axis model preserves combinations that the previous resolver lost:

| Source coverage | Viewport result | Meaning |
|---|---|---|
| 1911 raw `村镇` `TIME_SLICE`, `SUPPORTED` | `HAS_RECORDS` | Show real 1911 snapshot records in the viewport |
| 1911 raw `村镇` `TIME_SLICE`, `SUPPORTED` | `NO_RECORDS` | A 1911 snapshot exists, but this viewport has no eligible snapshot records |
| High-admin `LIMITED` | `HAS_RECORDS` | Show real records and warn that family coverage is limited |
| High-admin `LIMITED` | `NO_RECORDS` | Coverage is limited and the current viewport query is empty; neither fact overwrites the other |
| Settlement `UNSUPPORTED` | `NO_RECORDS` | The current source has no settlement-family component for this year; no claim about historical settlement existence |
| Raw `亭` `TIME_SERIES`, `UNKNOWN` | `HAS_RECORDS` | Show real interval records while avoiding a completeness claim |

## Family-resolution rules

### Settlement

1. Resolve raw `亭` interval records and raw `村镇` snapshots independently.
2. Union exact-year-valid records; never hide one component because another is unsupported.
3. At 1820 and 1911, identify only the raw `村镇` component as a snapshot.
4. At 14..22 and 623..959, retain real raw `亭` interval records. The source temporal model is `TIME_SERIES`; broader settlement completeness is `UNKNOWN`.
5. In all remaining years, no current settlement component claims coverage, so source support is `UNSUPPORTED`.

### High admin

1. Preserve raw-type differences and all exact-year-valid records.
2. Set family-level support to `LIMITED`; do not generate precise sparse intervals.
3. Do not infer `TIME_SLICE` from a one-year record.
4. Keep the 1820/1911 named province snapshot evidence in provenance diagnostics only until frozen-index records can be mapped to source layers.

### Regional admin and county

Their canonical records use interval validity and therefore provide `TIME_SERIES` components. Any completeness assertion still comes from source metadata, not record count. `NO_RECORDS` may be shown as a viewport result only when the current year has positive source support or globally active component records.

### Other

`other` contains heterogeneous source types and receives no broad completeness claim. Real exact-year-valid records remain visible. Source support defaults to `UNKNOWN`, while viewport result remains independently observable.

### Polity

`polity` remains Developer Mode only and is excluded from User Mode coverage labels.

## Canonical envelope rules

1. Read all valid `valid_from` and `valid_to` values from the exact frozen canonical processed index.
2. Compute global minimum and maximum without applying the TGAZ documentation envelope.
3. Record the processed-index SHA-256 beside the computed result.
4. Derive per-family and per-component observed periods separately; a global envelope does not imply that every family is covered throughout it.
5. Omit year zero from timeline presentation according to existing BCE/CE semantics, without rewriting intervals that span the numeric boundary.
6. If the canonical index changes, recompute all observed envelopes and require an explicit new freeze; never silently retain `-763..1912` as a version-independent constant.

## Planned metadata shape

After design approval, implementation may create independently versioned coverage metadata. This revision does not create it.

The future source metadata must contain:

- schema version;
- frozen canonical index path, size, record count, and SHA-256;
- computed global envelope;
- TGAZ documentation envelope as provenance note only;
- one entry per display family;
- explicit components keyed by exact raw source types;
- component temporal model and supported periods;
- source evidence and evidence strength;
- family-level support assessment;
- concise User Mode copy and fuller Developer Mode explanation.

The frontend must validate required fields and fail conservatively. Missing or malformed metadata produces no historical-absence claim and must not hide historical records.

## User Mode behavior

The existing single-line legend remains the layer switcher. Coverage text appears only for an enabled family and only when special or exceptional:

- raw `村镇` snapshot active: `1820 村镇快照` or `1911 村镇快照`;
- source family unsupported: `当前来源无该时期资料`;
- high-admin limited: `高层级资料有限`;
- heterogeneous/unknown coverage when a warning is useful: `来源覆盖未明`;
- viewport empty despite positive or limited source coverage: `当前范围无记录`.

Multiple facts may coexist. For example, an enabled 1911 settlement layer with no viewport candidates may show `1911 村镇快照 · 当前范围无记录`. An enabled high-admin layer with records may show `高层级资料有限` while retaining those records.

Normal positively supported time-series coverage adds no text. Disabled families show no coverage warning. Tooltips must explicitly say that the status describes the current source, not historical nonexistence. No modal, popup, large explanatory panel, or new map overlay is introduced.

## Developer Mode diagnostics

Developer Mode shows, per family and component:

- source coverage `support`;
- active `temporal_models`;
- exact raw types;
- supported or observed periods;
- snapshot years backed by source-layer evidence;
- global current-year active source count;
- current viewport eligible count;
- final displayed-unit count;
- `ViewportResult`;
- evidence and reason.

Diagnostics do not change feature eligibility, identity, co-location, layer toggles, or rendering.

## Data flow

1. Validate future coverage metadata against the frozen processed-index SHA and recomputed envelope.
2. Resolve source coverage per component for the current exact year.
3. Query all exact-year-valid historical records normally.
4. Apply explicit user family toggles without consulting coverage warnings.
5. Compute `ViewportResult` from eligible records.
6. Render real records regardless of `LIMITED` or `UNKNOWN` coverage.
7. Render concise coverage and viewport messages as independent facts.

Timeline movement only recomputes small in-memory assessments and queries. It does not download data, extend snapshots, mutate source records, or clear retained historical markers.

## Failure behavior

- Missing or malformed coverage metadata must never be interpreted as historical absence.
- Coverage failure must never hide an otherwise eligible historical record.
- The map and historical points remain usable if coverage metadata fails to load.
- User Mode omits unsubstantiated absence claims.
- Developer Mode reports the metadata validation problem.
- Zero global or viewport count does not automatically produce `LIMITED`, `UNKNOWN`, or `UNSUPPORTED`; those source states require metadata evidence.

## QA and testing design

Implementation must follow test-driven development after separate approval.

### Python QA

- Verify the frozen processed-index SHA before coverage generation.
- Recompute and assert the current envelope `-763..1912` from records rather than constants.
- Verify the TGAZ documentation range is provenance only and does not reject `hvd_70930` or 1912-ending records.
- Audit all settlement-family raw types and reject an unaccounted registry type.
- Reconcile raw `村镇` snapshot counts and raw `亭` interval periods.
- Reject count-only high-admin sparse interval claims.
- Verify no historical input checksum changes.

### Vitest

- Settlement 14, 626, and 750 retains interval records and does not show unsupported copy.
- Settlement 1819/1820/1821 and 1910/1911 resolves raw `村镇` snapshots without interpolation.
- Snapshot + `NO_RECORDS` remains representable.
- `LIMITED` + `HAS_RECORDS` remains representable and does not suppress points.
- High admin does not emit the former precise sparse intervals.
- Disabled layers return no User Mode warning.
- Coverage status updates immediately with exact-year changes.
- Coverage resolution does not mutate source feature objects.
- Missing metadata fails conservatively.

### Playwright

- Real `亭` records remain visible at representative interval years.
- Settlement 1819 → 1820 → 1821 and 1910 → 1911 shows only named raw `村镇` snapshots at exact years.
- A snapshot with an empty viewport displays both source and viewport facts.
- High-admin records remain visible while limited-coverage copy is present.
- Disabled layers show no warning.
- Existing legend and overlay non-overlap guarantees remain unchanged.

### Regression commands

- Full Python test suite.
- Full Vitest suite.
- Full Playwright suite.
- Production TypeScript/Vite build.

## Answers required by design review

1. **Settlement raw types:** exactly `村镇` and `亭`.
2. **Temporal components:** raw `村镇` is a named 1820/1911 snapshot component; raw `亭` contains interval records at 14..22 and 623..959.
3. **Years 14, 626, 750:** display the real exact-year-valid `亭` records; never label the family unsupported and never hide them.
4. **Canonical envelope:** `-763..1912`, derived from the 71,393-record frozen compact index with SHA-256 `7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf`.
5. **High-admin evidence:** Phase 1.4 supports a general `LIMITED` assessment but not exact sparse intervals; the former three intervals are removed.
6. **State axes:** source coverage and viewport result are separate. Source coverage is component-aware and preserves mixed temporal models; viewport result independently records `HAS_RECORDS` or `NO_RECORDS`.
7. **Avoiding historical-absence claims:** all copy names the current source or current viewport, warnings never suppress records, unsupported coverage is not equated with historical nonexistence, and tooltips state that distinction explicitly.

## Reporting and gate

After implementation approval, the phase report must answer the product questions above and confirm that historical source facts remain unchanged. The future implementation gate remains `PASS`, `PASS_WITH_OPEN_COVERAGE_ISSUES`, or `BLOCKED`.

This design revision itself is ready for implementation review only after its frozen-index evidence and internal consistency checks pass. No implementation starts automatically.
