# Data sources

ChronoChina is open-source software, not an open historical-data bundle. The
pipeline can acquire or query third-party sources, but those sources keep
their own licenses and access conditions.

This page is an engineering inventory, not legal advice. Recheck the official
terms before any public deployment, redistribution, or commercial use.

## Current sources

| Source | Purpose | Programmatic path | License/access note | Commercial status | Bundled here |
|---|---|---|---|---|---|
| TGAZ / CHGIS 2016 CSV snapshot | Canonical historical point index through 1911 | Upstream public CSV URL used by `chronochina.cli g0` | Dataset rights are separate from repository software rights; CHGIS terms are non-commercial and restrict Internet redistribution | Not cleared; separate commercial agreement required | No |
| TGAZ canonical API | Detail enrichment and provenance spot checks | Read-only JSON endpoint with local raw-once cache | Responses observed by the project identify CC BY-NC 4.0; respect request rate and source-specific terms | Not permitted where CC BY-NC applies | No |
| GeoNames CN dump | Modern anchor coordinates | Official country-dump download | CC BY 4.0 with attribution | Allowed with license compliance | No |
| CHGIS V6 | County/prefecture parity research | Harvard Dataverse API | Archive README/EULA is stricter than repository metadata: academic/non-commercial and no redistribution; commercial license required | Not cleared; separate commercial agreement required | No |
| Hartwell China Historical GIS | Static administrative snapshot research | Harvard Dataverse API | Archive terms conflict with metadata; apply the stricter non-commercial/share-alike/EULA interpretation | Not permitted by the stricter archive terms | No |
| CCTS | Candidate historical GIS source research | Account/application-based system | Published agreement restricts transfer and redistribution | Not permitted by published terms | No |
| OpenFreeMap / OpenMapTiles / OpenStreetMap | Optional modern reference layer | Remote vector tiles at runtime | Preserve attribution; OpenStreetMap data is ODbL and hosted-service terms apply | Allowed with attribution, ODbL, and service-term compliance | No |

## Verified official terms

The following official pages were rechecked on 2026-08-11:

- [Fudan CHGIS copyright statement](https://yugong.fudan.edu.cn/CHGIS/bqsm.htm): non-commercial academic/educational use only; commercial use requires a separate CHGIS agreement; Internet redistribution requires written permission.
- [TGAZ source repository](https://github.com/cga-harvard/tgaz): its GPL-3.0 statement applies to TGAZ software. It is not treated as a commercial or redistribution license for the historical record content obtained through CHGIS/TGAZ.
- [GeoNames export terms](https://www.geonames.org/export/): CC BY, attribution required, commercial use allowed.
- [OpenStreetMap copyright and license](https://www.openstreetmap.org/copyright): ODbL attribution and share-alike requirements apply to the map database.
- [OpenFreeMap terms](https://openfreemap.org/tos/): use of the hosted service accepts its current service terms; availability is not guaranteed.

Where dataset metadata, archive-internal terms, and source-site terms conflict, ChronoChina applies the stricter interpretation until the rights holder gives written clarification.

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
