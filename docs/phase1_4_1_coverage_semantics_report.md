# ChronoChina Phase 1.4.1 Coverage Semantics Report

Date: 2026-08-13
Gate: **PASS**

## Executive conclusion

Phase 1.4.1 implements the approved snapshot-aware, two-axis coverage model without changing historical source facts. User Mode now reports exceptional source coverage separately from the current viewport result; a warning never suppresses an exact-year-valid record and never claims that a historical unit did not exist. The complete Python, Vitest, production build, and Playwright suites pass.

## 1. Final coverage model

Coverage metadata is an independently versioned artifact validated against the exact canonical compact index. Runtime state has two orthogonal axes:

- **Source coverage assessment:** `SUPPORTED`, `UNSUPPORTED`, `LIMITED`, or `UNKNOWN`, plus zero or more active temporal models (`TIME_SERIES`, `TIME_SLICE`) and their source components.
- **Viewport result:** `HAS_RECORDS` or `NO_RECORDS`, computed only from exact-year-valid, enabled-family records in the current viewport.

The combination remains explicit. For example, `TIME_SLICE + SUPPORTED + NO_RECORDS` means that a source snapshot exists but the current viewport contains no eligible record; `LIMITED + HAS_RECORDS` retains real records while warning that coverage is incomplete.

Normal positively supported coverage adds no User Mode text. Disabled layers show no warning. Missing, malformed, or SHA-mismatched coverage metadata fails open: historical points remain usable and User Mode emits no unsupported-period claim.

## 2. Settlement snapshot and interval components

The settlement display family is the union of two independent components:

| Component | Raw type | Model | Evidence-backed periods | Records |
|---|---|---|---|---:|
| Raw town snapshots | `村镇` | `TIME_SLICE`, `SUPPORTED` | 1820 and 1911 only | 8,659 / 40,031 |
| Pavilion intervals | `亭` | `TIME_SERIES`, `UNKNOWN` completeness | 14–22 and 623–959 | 17 / 1 |

The resolver does not extend the 1820 or 1911 `村镇` snapshots to adjacent years. It also does not mark the whole settlement family unsupported when an exact-year-valid `亭` interval component exists.

## 3. Preservation at years 14, 626, and 750

The frozen compact index still contains and the UI regression suite still displays:

- Year 14: 17 active raw `亭` records, including `hvd_41144` 九江亭.
- Year 626: one active raw `亭` record, `hvd_115201` 杜邮亭.
- Year 750: the same exact-year-valid `hvd_115201` 杜邮亭.

Playwright uses the real local compact index and proves these records remain visible. They are represented as interval-based settlement-family records, not as `村镇` snapshots, and no unsupported message replaces or hides them.

## 4. Actual canonical time envelope

The generator derives the envelope from all valid `valid_from` / `valid_to` values in the frozen processed index:

- Path: `data/processed/explore/tgaz_compact.json`
- Size: 8,026,299 bytes
- Records: 71,393
- SHA-256: `7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf`
- Observed envelope: **-763 to 1912**

The TGAZ documentation range -222 to 1911 remains provenance only and does not clip canonical data.

## 5. Conservative high-admin semantics

`high_admin` contains raw `王畿`, `省`, `行省`, and `省级` records. Its family assessment is conservatively `LIMITED`. The implementation preserves all exact-year-valid records and exposes their observed periods in Developer Mode, but does not:

- infer a dataset snapshot from `BEG == END`;
- convert a zero/low yearly count into source sparsity;
- generate the former unsupported precise sparse intervals;
- equate historically different institutions with one continuous later-style provincial system.

Thus the UI may show “高层级资料有限” while still displaying real records. Precise completeness boundaries remain an open data-evidence question, not a product inference.

## 6. Unsupported source coverage versus an empty viewport

User Mode distinguishes the two conditions in source-explicit language:

- `UNSUPPORTED`: “当前来源无该时期资料” (compact visual badge: “来源无资料”). This describes the current source, not historical nonexistence.
- `NO_RECORDS` under supported/limited/active coverage: “当前范围无记录” (compact visual badge: “范围空”). This describes only the current viewport query.

Both facts can coexist, and snapshot identity is retained (for example, “1820 村镇快照 · 当前范围无记录”). Complete explanations remain in accessible names and tooltips; Developer Mode exposes support, temporal models, raw types, periods, source/global/viewport/display counts, viewport result, and evidence.

## 7. Historical source immutability

`data/qa/phase1_4_input_freeze.json` was read and verified in memory; no freeze writer was invoked. All 51 frozen paths were re-hashed and re-sized:

- 47 matched exactly.
- All 4/4 `canonical_historical_source` files matched exactly, including raw CSV, raw manifest, normalized JSONL, and compact index.
- Four code/UI paths differed and were reviewed explicitly:
  - `web/src/display/hierarchy.ts`: approved pure raw-type-to-family helper extraction; registry content is unchanged.
  - `web/src/App.tsx`: approved metadata loading, two-axis diagnostics, and lightweight coverage badges.
  - `web/src/styles.css`: approved responsive coverage-badge presentation.
  - `web/src/map/referenceLayers.ts`: the already-merged modern reference URL-validation security fix predates this phase branch and is unrelated to historical source facts.

No historical ID, coordinate, name, raw type, `BEG`, `END`, or provenance value was modified. The source and generated processed coverage metadata copies are byte-identical (SHA-256 `65e92238b9789b4b06da07efd5778efdff836006aed21033ad144d80085c3ea3`) and validate against the unchanged compact index.

## 8. Verification results

All commands were run fresh from the final Phase 1.4.1 head:

| Verification | Result | Measured duration / notes |
|---|---|---|
| `.\.venv\Scripts\python.exe -m pytest` | **110 passed**, exit 0 | pytest 18.02 s (21.4 s process wall time) |
| `npm.cmd test` | **15 files, 78 tests passed**, exit 0 | Vitest 6.20 s (7.3 s process wall time); JUnit artifact written |
| `npm.cmd run build` | **PASS**, exit 0 | TypeScript + Vite; 34 modules; Vite 653 ms |
| `npm.cmd run e2e` | **6 passed**, exit 0 | Chromium, one worker, 1.7 min (101.7 s process wall time) |
| `git diff --check` | **PASS**, exit 0 | no whitespace errors |

The initial sandboxed Vitest and build attempts could not write Vite temporary/build-info files (`EPERM` / access denied). The same commands passed in the approved normal Windows execution context; this is an execution-sandbox constraint, not a product or test failure.

The build retains the existing warning that the minified main JavaScript chunk is larger than 500 kB (1,204.57 kB; gzip 326.54 kB). It does not block correctness or Phase 1.4.1 acceptance.

Playwright regression evidence includes:

- exact snapshot transitions 1819 → 1820 → 1821 and 1910 → 1911;
- real interval settlement records at 14, 626, and 750;
- snapshot + empty viewport and limited high-admin + records combinations;
- enabled/disabled layer status behavior and rapid timeline updates;
- malformed metadata fail-open behavior;
- non-overlapping responsive overlays at 1440×900, 1024×768, and 900×1200.

## 9. Blockers and open limitations

**Blockers: none.**

Open, non-blocking limitations are evidence boundaries already made explicit by the product:

- settlement completeness outside the named `村镇` snapshots and observed `亭` intervals is not established;
- high-admin completeness is limited and cannot yet be assigned precise sparse periods;
- heterogeneous `other` coverage remains unknown;
- the existing production bundle-size warning remains outside this phase.

These limitations do not introduce historical-absence claims, mutate historical facts, hide real records, or block the approved Phase 1.4.1 behavior.

## Final gate

**PASS**

The approved design is implemented; snapshot and interval settlement semantics remain distinct; the actual canonical envelope is derived from the unchanged index; high-admin coverage is conservative; source coverage and viewport absence remain orthogonal; complete regression suites pass; and historical source facts remain unchanged.
