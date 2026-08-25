# Third-party notices

ChronoChina's Apache-2.0 license covers the software and project-authored
documentation in this repository. It does not relicense any historical data,
map data, hosted service, font, or third-party package.

## Runtime and build dependencies

The dependency manifests are the authoritative inventory:

- Python: `pyproject.toml`
- Web: `web/package.json` and `web/package-lock.json`

Principal direct dependencies include React, Vite, MapLibre GL JS, HTTPX,
PyShp, Shapely, and mapbox-vector-tile. Each remains under its upstream
license. Run the package-manager license tooling when preparing a binary
distribution, because transitive dependencies change over time.

## Historical and geographic sources

The following sources are referenced by the pipeline but are not distributed
in this repository:

- TGAZ / China Historical GIS (CHGIS), Harvard University and Fudan
  University. Dataset terms are separate from the software license. Some
  responses and distributed archives state non-commercial and
  no-redistribution restrictions.
- GeoNames country dump, licensed under CC BY 4.0.
- CHGIS V6 and Hartwell datasets from Harvard Dataverse. Repository metadata
  and archive-internal terms may conflict; ChronoChina applies the stricter
  archive terms and does not redistribute the archives.
- Chinese Civilization in Time and Space (CCTS), Academia Sinica. Published
  terms restrict transfer and redistribution.

Some regression tests mention a small number of upstream record identifiers
and short factual fields needed to reproduce historical-data edge cases. Those
references remain subject to upstream terms and are not relicensed under
Apache-2.0. No bulk historical dataset or API-response cache is bundled.

See `docs/data_sources.md` and `docs/data_redistribution_policy.md` before
downloading, using, publishing, or redistributing any generated dataset.

## Map reference layer

The Windows portable and locally generated Web build can include a China-bounded
PMTiles produced map extracted from an official Protomaps daily build, together
with Protomaps basemap fonts and sprites. The underlying map database includes
OpenStreetMap data under the Open Database License (ODbL); the application keeps
visible attribution to Protomaps and OpenStreetMap contributors. Bundled Noto
Sans font assets are distributed under the SIL Open Font License included with
the package. These assets remain under their upstream terms and are not
relicensed under Apache-2.0.
