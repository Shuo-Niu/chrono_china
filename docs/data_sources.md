# Data sources

ChronoChina is open-source software, not an open historical-data bundle. The
pipeline can acquire or query third-party sources, but those sources keep
their own licenses and access conditions.

This page is an engineering inventory, not legal advice. Recheck the official
terms before any public deployment, redistribution, or commercial use.

## Current sources

| Source | Purpose | Programmatic path | License/access note | Bundled here |
|---|---|---|---|---|
| TGAZ / CHGIS 2016 CSV snapshot | Canonical historical point index through 1911 | Upstream public CSV URL used by `chronochina.cli g0` | Dataset rights are separate from repository software rights; source/API materials include non-commercial terms | No |
| TGAZ canonical API | Detail enrichment and provenance spot checks | Read-only JSON endpoint with local raw-once cache | Responses observed by the project identify CC BY-NC 4.0; respect request rate and source-specific terms | No |
| GeoNames CN dump | Modern anchor coordinates | Official country-dump download | CC BY 4.0 with attribution | No |
| CHGIS V6 | County/prefecture parity research | Harvard Dataverse API | Archive README/EULA is stricter than repository metadata: academic/non-commercial and no redistribution; commercial license required | No |
| Hartwell China Historical GIS | Static administrative snapshot research | Harvard Dataverse API | Archive terms conflict with metadata; apply the stricter non-commercial/share-alike/EULA interpretation | No |
| CCTS | Candidate historical GIS source research | Account/application-based system | Published agreement restricts transfer and redistribution | No |
| OpenFreeMap / OpenMapTiles / OpenStreetMap | Optional modern reference layer | Remote vector tiles at runtime | Preserve attribution; OpenStreetMap data is ODbL | No |

## Coverage semantics

- Current CHGIS village/town records are principally the 1820 and 1911 time
  slices. Missing years do not mean that settlements did not exist.
- CHGIS V6 updates county and prefecture time-series layers but does not turn
  the 1820/1911 town layers into continuous settlement coverage.
- Data through 1911 and data for 1912–1949 have different access conditions.
- A time slice is never presented as continuous time-series coverage.

## Provenance requirements

Generated records must retain, where available:

- upstream source and URL;
- retrieval timestamp and checksum;
- canonical source ID/URI;
- raw name and feature type;
- source coordinates and validity interval;
- license/attribution information;
- parser warnings and explicit quarantine reasons.

Do not infer Historical Lineage from name similarity or spatial proximity.
