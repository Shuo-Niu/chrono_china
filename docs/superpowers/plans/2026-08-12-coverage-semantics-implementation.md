# ChronoChina Phase 1.4.1 Coverage Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement independent, snapshot-aware source coverage metadata and a two-axis User Mode status that never converts source or viewport absence into historical absence.

**Architecture:** A Python generator derives and validates a versioned metadata artifact from the frozen compact index without rewriting it. A pure TypeScript coverage module parses that artifact, resolves source coverage per raw-type component, and combines it orthogonally with per-family viewport results. `App.tsx` loads metadata independently from historical data, renders compact status badges in the existing layer switcher, and exposes full diagnostics only in Developer Mode.

**Tech Stack:** Python 3.11+, pytest, TypeScript 7, React 19, Vitest, Playwright, Vite, MapLibre GL JS.

## Global Constraints

- The approved design at `docs/superpowers/specs/2026-08-12-coverage-semantics-design.md` is authoritative.
- Keep the TGAZ/CHGIS 2016 snapshot as canonical; do not add sources, migrate V6, or add historical content.
- Coverage metadata stays independent from historical records and must not change IDs, coordinates, names, raw types, `BEG`/`END`, or provenance.
- Settlement contains raw `村镇` snapshots and raw `亭` interval records; never suppress one component because the other is inactive.
- Compute the canonical envelope from the frozen processed index. `-763..1912` is evidence for the current SHA, not a version-independent constant.
- Never derive high-admin sparse intervals from yearly counts. Use the approved `LIMITED` family assessment.
- Source coverage and viewport result are orthogonal; snapshot + empty viewport and limited + records must remain representable.
- Metadata failure must not block or clear historical records and must not create User Mode absence claims.
- Preserve timeline, manual toggles, display mode, basemap modes, responsive overlays, co-location, and incremental marker rendering.
- Follow strict red-green TDD for each production behavior.

---

### Task 1: Deterministic coverage metadata and Python QA

**Files:**
- Create: `pipeline/chronochina/qa/coverage_metadata.py`
- Create: `pipeline/tests/test_coverage_metadata.py`
- Create: `data/metadata/historical_layer_coverage.json`
- Generate locally: `data/processed/coverage/historical_layer_coverage.json`
- Generate locally: `data/qa/phase1_4_1_coverage_metadata_evidence.json`
- Modify: `pipeline/chronochina/cli.py`
- Create: `scripts/run_phase1_4_1_coverage.ps1`

**Interfaces:**
- `load_compact_index(path: Path) -> dict[str, object]`
- `derive_canonical_identity(path: Path, payload: Mapping[str, object]) -> dict[str, object]`
- `build_coverage_metadata(compact_path: Path) -> dict[str, object]`
- `validate_coverage_metadata(metadata: Mapping[str, object], compact_path: Path) -> None`
- `generate(repo_root: Path = PROJECT_ROOT) -> dict[str, object]`
- CLI command: `phase1-4-1-coverage`

- [ ] **Step 1: Write failing schema, envelope, component, and immutability tests**

Use literal assertions against the real frozen index and small controlled fixtures:

```python
def test_real_frozen_index_derives_identity_without_documentation_clipping() -> None:
    metadata = build_coverage_metadata(COMPACT_PATH)
    identity = metadata["canonical_index"]
    assert identity["record_count"] == 71_393
    assert identity["sha256"] == "7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf"
    assert identity["observed_envelope"] == {"min_year": -763, "max_year": 1912}
    assert metadata["provenance"]["tgaz_documentation_envelope"] == {
        "min_year": -222,
        "max_year": 1911,
        "role": "provenance_note_only",
    }

def test_settlement_components_preserve_snapshot_and_interval_models() -> None:
    metadata = build_coverage_metadata(COMPACT_PATH)
    components = {item["id"]: item for item in metadata["families"]["settlement"]["components"]}
    assert components["raw_town_snapshots"]["raw_types"] == ["村镇"]
    assert components["raw_town_snapshots"]["temporal_model"] == "TIME_SLICE"
    assert components["raw_town_snapshots"]["snapshot_years"] == [1820, 1911]
    assert components["raw_pavilion_intervals"]["raw_types"] == ["亭"]
    assert components["raw_pavilion_intervals"]["temporal_model"] == "TIME_SERIES"
    assert components["raw_pavilion_intervals"]["supported_periods"] == [[14, 22], [623, 959]]

def test_metadata_generation_does_not_modify_frozen_index(tmp_path: Path) -> None:
    compact = tmp_path / "tgaz_compact.json"
    compact.write_bytes(COMPACT_PATH.read_bytes())
    before = sha256_file(compact)
    build_coverage_metadata(compact)
    assert sha256_file(compact) == before
```

Also test malformed schema rejection, unaccounted settlement raw types, exact 8,659/40,031 snapshot counts, exact 17/1 `亭` counts, all four high-admin raw types, `LIMITED` without sparse-period fields, and metadata/index SHA or envelope mismatch rejection.

- [ ] **Step 2: Run the focused Python test and confirm RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest pipeline/tests/test_coverage_metadata.py -q
```

Expected: collection/import failure because `chronochina.qa.coverage_metadata` does not exist.

- [ ] **Step 3: Implement the minimal deterministic generator and validator**

Use `chronochina.io.sha256_file` and `write_json`. Parse tuples through their declared `fields`; derive the envelope and counts from records. Encode only evidence approved by the design:

```python
SETTLEMENT_COMPONENTS = (
    {
        "id": "raw_town_snapshots",
        "raw_types": ["村镇"],
        "temporal_model": "TIME_SLICE",
        "support": "SUPPORTED",
        "snapshot_years": [1820, 1911],
    },
    {
        "id": "raw_pavilion_intervals",
        "raw_types": ["亭"],
        "temporal_model": "TIME_SERIES",
        "support": "UNKNOWN",
        "supported_periods": [[14, 22], [623, 959]],
    },
)
```

High admin contains `王畿`, `省`, `行省`, `省级`, has family `default_support: "LIMITED"`, preserves observed components, and contains no `sparse_periods`. Generate one deterministic payload to both `data/metadata/historical_layer_coverage.json` and `data/processed/coverage/historical_layer_coverage.json`, plus QA evidence containing the source/index reconciliation and unchanged SHA.

- [ ] **Step 4: Add the CLI command and PowerShell wrapper**

Add a lazy import branch in `cli.py` and a wrapper equivalent to:

```powershell
$ProjectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $ProjectRoot ".venv\Scripts\python.exe") -m chronochina.cli phase1-4-1-coverage
if ($LASTEXITCODE -ne 0) { throw "Phase 1.4.1 coverage metadata generation failed." }
```

- [ ] **Step 5: Run RED→GREEN verification and generate artifacts**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest pipeline/tests/test_coverage_metadata.py -q
.\.venv\Scripts\python.exe -m chronochina.cli phase1-4-1-coverage
.\.venv\Scripts\python.exe -m pytest pipeline/tests/test_coverage_metadata.py pipeline/tests/test_phase1_3_1f.py pipeline/tests/test_phase1_4.py -q
```

Expected: all focused tests pass; generated source and processed metadata validate against the unchanged frozen compact SHA.

- [ ] **Step 6: Commit Task 1**

```powershell
git add pipeline/chronochina/qa/coverage_metadata.py pipeline/tests/test_coverage_metadata.py pipeline/chronochina/cli.py scripts/run_phase1_4_1_coverage.ps1 data/metadata/historical_layer_coverage.json
git commit -m "feat: generate snapshot-aware coverage metadata"
```

---

### Task 2: Pure two-axis TypeScript coverage model

**Files:**
- Create: `web/src/coverage/sourceCoverage.ts`
- Create: `web/src/coverage/sourceCoverage.test.ts`
- Modify: `web/src/display/hierarchy.ts`
- Modify: `web/src/explore/viewportQuery.ts`
- Modify: `web/src/explore/viewportQuery.test.ts`

**Interfaces:**
- `parseCoverageMetadata(value: unknown, index: CompactHistoricalIndex): CoverageMetadata`
- `assessSourceCoverage(metadata: CoverageMetadata | null, family: DisplayFamily, year: number): SourceCoverageAssessment`
- `resolveViewportResult(features: readonly HistoricalFeature[], family: DisplayFamily): ViewportResult`
- `userCoverageMessages(assessment: SourceCoverageAssessment, viewport: ViewportResult, enabled: boolean): readonly CoverageMessage[]`
- `displayFamilyFromRawType(rawType: string): DisplayFamily`
- `ViewportQueryResult.viewportResult: "HAS_RECORDS" | "NO_RECORDS"`

- [ ] **Step 1: Write failing pure-model tests**

Use hand-built complete metadata and compact-index fixtures. Test the exact behavior:

```typescript
expect(assessSourceCoverage(metadata, "settlement", 1819).support).toBe("UNSUPPORTED");
expect(assessSourceCoverage(metadata, "settlement", 1820).temporalModels).toEqual(["TIME_SLICE"]);
expect(assessSourceCoverage(metadata, "settlement", 1821).support).toBe("UNSUPPORTED");
expect(assessSourceCoverage(metadata, "settlement", 626)).toMatchObject({
  support: "UNKNOWN",
  temporalModels: ["TIME_SERIES"],
});
expect(assessSourceCoverage(metadata, "high_admin", 750).support).toBe("LIMITED");
expect(userCoverageMessages(snapshotAssessment, "NO_RECORDS", true).map((item) => item.text))
  .toEqual(["1820 村镇快照", "当前范围无记录"]);
expect(userCoverageMessages(unsupportedAssessment, "NO_RECORDS", false)).toEqual([]);
```

Cover 14/626/750, 1819/1820/1821, 1910/1911, malformed/SHA-mismatched metadata, missing metadata, limited + records, snapshot + no records, disabled layer, and frozen input objects before/after resolution.

- [ ] **Step 2: Run focused Vitest and confirm RED**

Run:

```powershell
Set-Location web
npm.cmd exec vitest run src/coverage/sourceCoverage.test.ts
```

Expected: failure because the coverage module does not exist.

- [ ] **Step 3: Implement pure parser and resolver**

Use discriminated literal types:

```typescript
export type TemporalModel = "TIME_SERIES" | "TIME_SLICE";
export type SourceSupport = "SUPPORTED" | "UNSUPPORTED" | "LIMITED" | "UNKNOWN";
export type ViewportResult = "HAS_RECORDS" | "NO_RECORDS";

export interface SourceCoverageAssessment {
  family: DisplayFamily;
  year: number;
  support: SourceSupport;
  temporalModels: readonly TemporalModel[];
  activeComponents: readonly SourceCoverageComponent[];
  diagnostic: string | null;
}
```

Metadata `null` or parser failure resolves to `UNKNOWN` with a diagnostic, but `userCoverageMessages` returns no User Mode absence warning for that failure. Preserve snapshot + viewport and limited + viewport as separate values.

- [ ] **Step 4: Separate viewport results from source coverage in the query module**

Replace the count-derived `ViewportCoverageStatus` output with:

```typescript
const viewportResult: ViewportResult = active.length > 0 ? "HAS_RECORDS" : "NO_RECORDS";
```

Do not infer source support, historical absence, or high-admin sparsity inside `queryCompactIndex`. Keep exact-year spatial filtering, counts, latency, and feature conversion unchanged.

- [ ] **Step 5: Run focused and neighboring tests GREEN**

```powershell
npm.cmd exec vitest run src/coverage/sourceCoverage.test.ts src/explore/viewportQuery.test.ts src/display/hierarchy.test.ts
```

Expected: all focused tests pass and feature objects remain deeply equal before and after coverage assessment.

- [ ] **Step 6: Commit Task 2**

```powershell
git add web/src/coverage/sourceCoverage.ts web/src/coverage/sourceCoverage.test.ts web/src/display/hierarchy.ts web/src/explore/viewportQuery.ts web/src/explore/viewportQuery.test.ts
git commit -m "feat: separate source coverage from viewport results"
```

---

### Task 3: Independent metadata loading and lightweight User Mode statuses

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `web/src/styles.css`

**Interfaces:**
- Fetch path: `/coverage/historical_layer_coverage.json`
- Map diagnostics: `data-coverage-metadata-status`, `data-coverage-family-states`, `data-explore-viewport-result`
- Status selector: `[data-coverage-family="<family>"]`

- [ ] **Step 1: Extend the App fixture and write failing integration tests**

Add a complete coverage metadata response to `installFetchMock`. Test observable behavior, not fetch calls:

```typescript
expect(screen.getByTestId("coverage-settlement")).toHaveTextContent("1911 村镇快照");
expect(screen.getByTestId("coverage-high_admin")).toHaveTextContent("资料覆盖有限");
await userEvent.click(screen.getByRole("button", { name: /村镇、亭/ }));
expect(screen.queryByTestId("coverage-settlement")).not.toBeInTheDocument();
```

Add timeline cases for 1819/1820/1821, 1910/1911, and 14/626/750. At 14/626/750 assert real `亭` marker IDs remain eligible and no unsupported message appears. Add malformed metadata response and assert the existing map points remain interactive while User Mode emits no unsubstantiated absence message.

- [ ] **Step 2: Run App tests and confirm RED**

```powershell
Set-Location web
npm.cmd exec vitest run src/App.test.tsx
```

Expected: failure because coverage metadata is not loaded or rendered.

- [ ] **Step 3: Load metadata independently**

Fetch only after the compact index is ready, parse against that exact index, and keep states `idle | loading | ready | failed`. A failed coverage fetch/parser must not change `exploreIndex`, `exploreResult`, `activeCollection`, enabled families, or markers.

- [ ] **Step 4: Compute per-family orthogonal states without changing eligibility**

For each User Mode family, derive global active count from the compact records, viewport count from exact-year query features, `SourceCoverageAssessment` from metadata, and `ViewportResult` independently. Do not pass coverage results into `selectSemanticZoomUnits`.

- [ ] **Step 5: Render compact statuses in the existing switcher**

Render an abbreviated badge inside each enabled family button and put the complete explanation in `title`/accessible text. Use source-explicit wording:

```tsx
<span
  className="legend__coverage"
  data-coverage-family={config.id}
  data-testid={`coverage-${config.id}`}
  title={messages.map((message) => message.explanation).join("；")}
>
  {messages.map((message) => message.text).join(" · ")}
</span>
```

Normal supported time series and disabled families render no badge. Add Developer Mode component diagnostics to the existing explore panel. Keep the legend one line, with no scrollbar, and use compact typography rather than a new panel.

- [ ] **Step 6: Run App, full Vitest, and build GREEN**

```powershell
npm.cmd exec vitest run src/App.test.tsx src/coverage/sourceCoverage.test.ts src/explore/viewportQuery.test.ts
npm.cmd test
npm.cmd run build
```

Expected: all unit tests pass, TypeScript/Vite build succeeds, and no existing marker/timeline/basemap tests regress.

- [ ] **Step 7: Commit Task 3**

```powershell
git add web/src/App.tsx web/src/App.test.tsx web/src/styles.css
git commit -m "feat: show source-aware layer coverage states"
```

---

### Task 4: Real-data Playwright regression and responsive safety

**Files:**
- Create: `web/tests/e2e/phase1_4_1.spec.ts`

**Interfaces:**
- Reuse `data-testid="timeline-range"`, `data-testid="map"`, `[data-legend-family]`, `[data-coverage-family]`, and `window.__CHRONOCHINA_QA_MAP__`.

- [ ] **Step 1: Write the real-data E2E spec and confirm it fails before integration is present**

Use the native range setter and `input` events. Cover:

```typescript
await setYear(page, 1819);
await expect(page.locator('[data-coverage-family="settlement"]')).toContainText("当前来源无该时期资料");
await setYear(page, 1820);
await expect(page.locator('[data-coverage-family="settlement"]')).toContainText("1820 村镇快照");
await setYear(page, 1821);
await expect(page.locator('[data-coverage-family="settlement"]')).toContainText("当前来源无该时期资料");
```

Repeat 1910→1911. Jump to `[108.85463, 34.41219]` and test 626/750 for visible `hvd_115201` raw `亭`; at 14 use a known raw `亭` viewport or assert the global component count diagnostic is 17. Toggle settlement off/on and verify warning removal/restoration. Dispatch rapid input events and assert the status follows the final year with zero stale commits and zero full-layer clears.

- [ ] **Step 2: Add overlay collision assertions at supported viewports**

At minimum rerun 1440×900, 1024×768, and 900×1200. Assert the legend remains one line, has no scrollbars, and does not intersect the timeline, controls, attribution, or an open detail panel.

- [ ] **Step 3: Run the new E2E spec then the full E2E suite**

```powershell
Set-Location web
npm.cmd run e2e -- --grep "Phase 1.4.1"
npm.cmd run e2e
```

Expected: settlement snapshot/interval/toggle/drag assertions pass and all prior active E2E specs remain green.

- [ ] **Step 4: Commit Task 4**

```powershell
git add web/tests/e2e/phase1_4_1.spec.ts
git commit -m "test: cover snapshot-aware layer statuses"
```

---

### Task 5: Freeze verification, report, and final gate

**Files:**
- Create: `docs/phase1_4_1_coverage_semantics_report.md`

**Interfaces:**
- Gate values: `PASS`, `PASS_WITH_OPEN_COVERAGE_ISSUES`, or `BLOCKED`.

- [ ] **Step 1: Verify historical immutability without rewriting the freeze file**

Read `data/qa/phase1_4_input_freeze.json`, recompute every frozen file SHA/size, and compare in memory. Do not invoke a verifier that rewrites the freeze artifact. At minimum confirm compact SHA remains `7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf`.

- [ ] **Step 2: Run complete verification**

```powershell
.\.venv\Scripts\python.exe -m pytest
Set-Location web
npm.cmd test
npm.cmd run build
npm.cmd run e2e
```

Record exact counts, durations, exit codes, and any warnings. Do not claim PASS from partial suites.

- [ ] **Step 3: Write the phase report**

Answer all nine required questions with direct evidence: two-axis model; settlement components; preserved 14/626/750 records; derived `-763..1912` envelope; conservative high-admin handling; unsupported versus covered-no-records copy; unchanged historical facts; exact test results; blockers.

- [ ] **Step 4: Commit Task 5**

```powershell
git add docs/phase1_4_1_coverage_semantics_report.md
git commit -m "docs: report Phase 1.4.1 coverage semantics"
```

- [ ] **Step 5: Final branch review and gate**

Review the full branch diff against the approved design, resolve all Critical/Important findings, rerun affected tests, and emit only the evidence-supported gate. Stop after reporting; do not investigate sources or start another phase.
