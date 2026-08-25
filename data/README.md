# Local data workspace

ChronoChina does not redistribute third-party historical data or generated
record-level derivatives. The public repository contains directory
placeholders plus explicitly reviewed, project-authored artifacts:

- `data/metadata/historical_layer_coverage.json` contains aggregate source-coverage
  semantics and counts, without record-level IDs, names, coordinates, or source rows.
- `data/knowledge/drafts/`, `data/knowledge/reviews/`, and the allowlisted
  `data/processed/knowledge/` publication contain original institutional
  explanations, review decisions, citations, and matching rules. They do not
  contain CHGIS/TGAZ source rows.

These narrow exceptions do not permit publishing any record-level input or
generated historical derivative.

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
