# Local data workspace

This directory is intentionally empty in the public repository. ChronoChina
does not redistribute third-party historical data or generated record-level
derivatives.

The pipeline creates:

```text
raw/          downloaded source artifacts and API caches
intermediate/ normalized local indexes
processed/    Web-consumable local datasets
qa/           local data and regression evidence
```

Run the documented pipeline commands to populate these directories after
reviewing `docs/data_sources.md` and `docs/data_redistribution_policy.md`.
Never commit generated contents from these directories.
