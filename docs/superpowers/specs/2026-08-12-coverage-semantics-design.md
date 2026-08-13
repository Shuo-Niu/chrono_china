# ChronoChina Phase 1.4.1 Coverage Semantics Design

## Goal

Make User Mode distinguish source coverage from historical absence without changing any historical source fact. Coverage semantics are independent metadata describing what the current canonical source can support for each display family and year.

## Scope and constraints

- Keep the current TGAZ/CHGIS 2016 snapshot as the canonical historical source.
- Do not add or migrate data sources, including CHGIS V6.
- Do not modify raw or normalized records, coordinates, IDs, names, feature types, provenance, or `BEG`/`END`.
- Preserve viewport-driven exploration, continuous exact-year navigation, manual layer toggles, co-location rules, marker alignment, basemap behavior, and incremental rendering.
- User Mode shows coverage text only for exceptional or special states. Normal time-series coverage adds no text.
- Developer Mode may show full coverage diagnostics.

## Approaches considered

### 1. Hard-code coverage rules in React

This is the smallest immediate code change, but it couples data facts to presentation code and allows Phase 1.4 audit evidence and User Mode behavior to drift. Rejected.

### 2. Infer coverage from current-year record counts

This is mechanically simple, but a zero count cannot distinguish an unsupported period from a covered period with no records. It would recreate the semantic error this phase exists to fix. Rejected.

### 3. Explicit metadata validated against Phase 1.4 evidence

Selected. A separate metadata artifact records source-backed coverage claims. Python QA validates those claims against frozen Phase 1.4 statistics, while TypeScript resolves the current family/year/view state without modifying historical records.

## Coverage model

The public coverage vocabulary is:

- `TIME_SERIES`: the source provides interval-based records for the family and year.
- `TIME_SLICE`: the source provides records only for a named snapshot year.
- `UNSUPPORTED_PERIOD`: the source does not claim coverage for the family and year.
- `SPARSE_COVERAGE`: the period is within the source's broad scope, but the audited family coverage is materially sparse.
- `COVERED_NO_RECORDS`: the family and year are covered, but the current viewport contains no eligible source records.

Coverage metadata is source-level evidence, not entity validity. It must not be embedded into or used to rewrite `HistoricalFeature` records.

### Family rules

| Display family | Source semantics | User Mode behavior |
|---|---|---|
| `settlement` | `TIME_SLICE` at 1820 and 1911 only; `UNSUPPORTED_PERIOD` in all other years | Show `1820 快照` or `1911 快照` at those years; otherwise show `该时期暂无资料` when enabled |
| `high_admin` | Source-backed interval records exist across parts of the canonical envelope, with audited sparse intervals at 208–458, 464–1219, and 1382–1643; the family also contains named 1820 and 1911 province snapshots | Show `该时期资料较少` in sparse intervals; show `含 1820 快照` or `含 1911 快照` at the two snapshot years; show `该时期暂无资料` outside the canonical envelope |
| `regional_admin` | Interval-based canonical time series within the canonical source envelope | No status for normal coverage; show `当前范围无记录` when covered but empty in the current viewport |
| `county` | Interval-based canonical time series within the canonical source envelope | No status for normal coverage; show `当前范围无记录` when covered but empty in the current viewport |
| `other` | Conservatively treated as source-derived interval records; no completeness claim beyond the canonical envelope | No status for normal coverage; show `当前范围无记录` only when the resolver has positive coverage evidence |
| `polity` | Developer-only and excluded from User Mode coverage labels | Developer diagnostics only |

The canonical supported envelope is read from the existing processed index metadata when available and validated against the audited range `-222..1911`. Coverage metadata must not silently expand that envelope.

## State resolution

Coverage is resolved independently for every display family using:

1. whether the user enabled the family;
2. current exact year;
3. explicit source metadata for that family;
4. current-year active source count for that family;
5. current viewport eligible count for that family.

Resolution priority is:

1. disabled layer: return no User Mode status;
2. year outside supported metadata: `UNSUPPORTED_PERIOD`;
3. explicit sparse interval: `SPARSE_COVERAGE`;
4. explicit snapshot year: `TIME_SLICE`;
5. positively covered year with zero viewport records: `COVERED_NO_RECORDS`;
6. otherwise: `TIME_SERIES`.

The ordering prevents a zero viewport count from overriding known unsupported, sparse, or snapshot semantics. It also prevents a snapshot from being extended to adjacent years.

For a mixed family such as `high_admin`, `TIME_SLICE` means the current year's family coverage materially includes a named snapshot layer; it does not claim that every displayed high-admin record is snapshot-only. Its tooltip must say that interval records may coexist with the named province snapshot. Settlement has no such mixture: its 1820 and 1911 records are snapshot-only.

## Metadata artifact

Create a small, independently versioned source JSON file at `data/metadata/historical_layer_coverage.json`. The pipeline validates it and publishes a byte-equivalent Web artifact at `data/processed/coverage/historical_layer_coverage.json`. It contains:

- schema version;
- canonical source identifier and audit provenance;
- canonical year envelope;
- one entry per display family;
- coverage kind;
- snapshot years;
- sparse intervals;
- concise User Mode labels;
- fuller explanatory text for tooltip and Developer Mode.

Vite already serves `data/processed/` as its public data tree. The frontend validates required fields and fails conservatively: invalid or unavailable coverage metadata produces no historical-absence claim and a Developer Mode diagnostic.

## User Mode UI

The existing single-line legend remains the layer switcher. Each enabled family may receive one compact status token beside its existing name:

- `1820 快照` / `1911 快照` for settlement
- `含 1820 快照` / `含 1911 快照` for the mixed high-admin family
- `该时期暂无资料`
- `该时期资料较少`
- `当前范围无记录`

Normal `TIME_SERIES` has no visible token. Disabled families have no coverage warning. A tooltip explains that the status describes source coverage rather than historical existence. No modal, popup, large explanatory panel, or new map overlay is introduced.

The compact token must preserve the existing supported-width legend contract. If the available row is too narrow, the status remains accessible through the button tooltip and an abbreviated visual token may be used, but family names must not be truncated, wrapped, hidden, or made scrollable.

## Developer Mode diagnostics

Developer Mode adds a compact table or list containing, per family:

- `coverage_kind`;
- source layer or family identifier;
- snapshot years;
- current-year active source count;
- source-supported count when available;
- current viewport count;
- resolved reason.

These values are diagnostic only and do not change display eligibility, feature identity, or layer toggle state.

## Data flow

1. The checked-in coverage metadata records Phase 1.4 source semantics.
2. The frontend loads it once with the existing static data assets.
3. Exact-year, viewport, and layer-toggle state feed a pure coverage resolver.
4. The resolver returns one status per family plus diagnostics.
5. The legend renders exceptional or special User Mode labels for enabled families.
6. Developer Mode renders complete resolver diagnostics.

Timeline movement only recomputes the small in-memory status map. It does not trigger data downloads or mutate the persistent historical marker registry.

## Failure behavior

- Missing or malformed coverage metadata must never be interpreted as historical absence.
- The map and historical points remain usable if the coverage artifact fails to load.
- User Mode omits unsupported claims when metadata cannot substantiate them.
- Developer Mode reports the metadata loading or validation problem.
- Coverage calculation must not throw when a family has zero current records.

## QA and testing

Implementation follows test-driven development.

### Python QA

- Validate the metadata schema and all display-family identifiers.
- Reconcile settlement snapshot years with Phase 1.4 evidence: 1820 and 1911 only.
- Validate high-admin sparse intervals against the audited canonical yearly counts.
- Verify interval ordering, no year zero, and no overlap that changes resolution priority unintentionally.
- Hash or deep-compare historical inputs before and after generation to prove no source fact changed.

### Vitest

- Settlement at 1819, 1820, 1821, 1910, and 1911.
- A normal time-series family.
- A sparse high-admin year.
- `COVERED_NO_RECORDS` only for a positively covered year and viewport.
- Disabled layers return no User Mode warning.
- Status updates immediately with exact-year changes.
- Coverage resolution does not mutate source feature objects.
- Missing metadata fails conservatively.

### Playwright

- Toggle settlement on and move 1819 → 1820 → 1821.
- Move 1910 → 1911 and observe the settlement snapshot state.
- Confirm disabled layers show no warning.
- Confirm sparse high-admin copy appears in a known sparse year.
- Confirm legend, timeline, map controls, and detail panel retain their non-overlap guarantees.

### Regression commands

- Full Python test suite.
- Full Vitest suite.
- Full Playwright suite.
- Production TypeScript/Vite build.

## Reporting and gate

Create `docs/phase1_4_1_coverage_semantics_report.md` answering:

1. which User Mode layers are time series;
2. which are time slices;
3. how 1820/1911 settlement snapshots are interpreted;
4. which high-admin periods are sparse;
5. how User Mode distinguishes unsupported coverage from covered empty viewports;
6. whether any historical source facts changed.

The final gate is `PASS`, `PASS_WITH_OPEN_COVERAGE_ISSUES`, or `BLOCKED`. No follow-on source research or content work starts in this phase.
