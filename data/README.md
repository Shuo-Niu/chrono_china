# Local data workspace

ChronoChina does not redistribute third-party historical data or generated
record-level derivatives. The public repository contains directory
placeholders plus one reviewed, project-authored aggregate artifact:

`data/metadata/historical_layer_coverage.json`

This metadata describes source-coverage semantics and aggregate counts. It
contains no record-level IDs, names, coordinates, or source rows. Its review
does not permit publishing any record-level input or generated derivative.

The pipeline creates:

```text
raw/          downloaded source artifacts and API caches
intermediate/ normalized local indexes
processed/    Web-consumable local datasets
qa/           local data and regression evidence
```

Run the documented pipeline commands to populate these directories after
reviewing `docs/data_sources.md` and `docs/data_redistribution_policy.md`.
Never commit generated record-level contents from these directories.
