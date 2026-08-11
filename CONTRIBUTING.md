# Contributing to ChronoChina

Thank you for contributing. ChronoChina treats historical identity,
provenance, time validity, and data licensing as correctness requirements.

## Before opening a pull request

1. Create a focused branch from `main`.
2. Keep Python dependencies inside `.venv/` and Node dependencies inside
   `web/node_modules/`.
3. Do not commit raw, intermediate, processed, or record-level QA data.
4. Add or update tests for behavioral changes.
5. Run `powershell -ExecutionPolicy Bypass -File .\scripts\test_public.ps1`.
6. Run `powershell -ExecutionPolicy Bypass -File .\scripts\release_audit.ps1`.

Full data and browser integration tests require locally acquired third-party
datasets and are intentionally separate from the public CI suite.

## Historical data rules

- `nearby != same entity`.
- A shared coordinate does not establish identity or lineage.
- A shared name does not establish identity.
- A name change does not establish a new entity.
- Spatial Neighborhood and Historical Lineage must remain separate.
- Never fabricate historical records or infer missing years from adjacent
  snapshots.
- Preserve source IDs, coordinates, names, time intervals, and provenance.
- Retain competing assertions; do not use newest-write-wins.

If a proposed data source has unclear access, attribution, redistribution, or
commercial-use terms, stop and document the uncertainty before integrating it.

## Pull request scope

Prefer small, reviewable changes. Do not combine product changes, data-source
migrations, and broad refactors in one pull request. Describe:

- the user-visible or pipeline outcome;
- the evidence and tests;
- any data or license impact;
- whether canonical historical facts changed.

Contributions submitted to this repository are accepted under Apache-2.0,
unless they are conspicuously marked as not being a contribution.
