from __future__ import annotations

import json
import math
import os
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx
import mapbox_vector_tile
import shapefile
from shapely import make_valid
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from chronochina.config import INTERMEDIATE_DIR, PROJECT_ROOT, RAW_DIR
from chronochina.io import USER_AGENT, read_json, sha256_file, utc_now, write_json
from chronochina.spatial import haversine


OPENFREEMAP_TILEJSON_URL = "https://tiles.openfreemap.org/planet"
MODERN_GEOGRAPHY_RAW_DIR = RAW_DIR / "modern_geography" / "openfreemap"
TILEJSON_PATH = MODERN_GEOGRAPHY_RAW_DIR / "tilejson.json"
SOURCE_MANIFEST_PATH = MODERN_GEOGRAPHY_RAW_DIR / "manifest.json"
V6_SHAPEFILE_PATH = (
    INTERMEDIATE_DIR
    / "chgis_v6"
    / "county_points"
    / "v6_time_cnty_pts_utf_wgs84.shp"
)


@dataclass(frozen=True)
class PlausibilityConfig:
    analysis_zoom: int = 9
    r1_reproduction_zoom: int = 7
    tile_padding: int = 1
    boundary_uncertainty_km: float = 0.5
    nearshore_max_km: float = 2.0
    moderate_offshore_max_km: float = 10.0
    phase1_2_map_zoom: float = 7.4
    maplibre_world_tile_size_px: int = 512
    history_dot_center_offset_px: float = 9.5


DEFAULT_CONFIG = PlausibilityConfig()


def _empty_geometry() -> BaseGeometry:
    return unary_union([])


def _projector(origin_lon: float, origin_lat: float):
    longitude_scale = 111.320 * math.cos(math.radians(origin_lat))

    def project(x: float, y: float, z: float | None = None):
        projected = ((x - origin_lon) * longitude_scale, (y - origin_lat) * 110.574)
        return (*projected, z) if z is not None else projected

    return project


@dataclass
class WaterMosaic:
    marine_wgs84: BaseGeometry
    inland_by_class_wgs84: dict[str, BaseGeometry]
    coverage_wgs84: BaseGeometry
    reference_source: dict[str, Any]
    origin_lon: float
    origin_lat: float

    def __post_init__(self) -> None:
        projector = _projector(self.origin_lon, self.origin_lat)
        self.marine_km = transform(projector, self.marine_wgs84)
        self.inland_by_class_km = {
            name: transform(projector, geometry)
            for name, geometry in self.inland_by_class_wgs84.items()
        }
        inland = list(self.inland_by_class_km.values())
        self.inland_km = unary_union(inland) if inland else _empty_geometry()
        water = [geometry for geometry in (self.marine_km, self.inland_km) if not geometry.is_empty]
        self.all_water_km = unary_union(water) if water else _empty_geometry()
        self.coverage_km = transform(projector, self.coverage_wgs84)

    @classmethod
    def from_geometries(
        cls,
        *,
        marine: BaseGeometry | None,
        inland_by_class: dict[str, BaseGeometry] | None = None,
        coverage: BaseGeometry | None = None,
        reference_source: dict[str, Any] | None = None,
        origin_lon: float = 0.0,
        origin_lat: float = 0.0,
    ) -> "WaterMosaic":
        return cls(
            marine_wgs84=marine or _empty_geometry(),
            inland_by_class_wgs84=inland_by_class or {},
            coverage_wgs84=coverage or box(-180, -90, 180, 90),
            reference_source=reference_source or {"dataset": "test_geometry"},
            origin_lon=origin_lon,
            origin_lat=origin_lat,
        )

    def point_km(self, lon: float, lat: float) -> Point:
        x, y = _projector(self.origin_lon, self.origin_lat)(lon, lat)
        return Point(x, y)


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    limited_lat = max(-85.05112878, min(85.05112878, lat))
    x = int((lon + 180.0) / 360.0 * n)
    y = int(
        (
            1
            - math.asinh(math.tan(math.radians(limited_lat))) / math.pi
        )
        / 2
        * n
    )
    return max(0, min(n - 1, x)), max(0, min(n - 1, y))


def _tile_latitude(y: float, zoom: int) -> float:
    n = 2**zoom
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    n = 2**zoom
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = _tile_latitude(y, zoom)
    south = _tile_latitude(y + 1, zoom)
    return west, south, east, north


def _tile_transformer(x: int, y: int, zoom: int, extent: int = 4096):
    n = 2**zoom

    def convert(local_x: float, local_y: float) -> tuple[float, float]:
        # mapbox-vector-tile's default decoder has already flipped MVT Y upward.
        global_x = x + local_x / extent
        global_y = y + (extent - local_y) / extent
        lon = global_x / n * 360.0 - 180.0
        lat = _tile_latitude(global_y, zoom)
        return lon, lat

    return convert


class OpenFreeMapWaterProvider:
    def __init__(self, *, pause_seconds: float = 0.04) -> None:
        self.pause_seconds = pause_seconds
        self._tilejson: dict[str, Any] | None = None
        self._touched_tiles: dict[str, dict[str, Any]] = {}

    def _download_once(self, client: httpx.Client, url: str, path: Path) -> str:
        if path.exists():
            return "existing_raw"
        path.parent.mkdir(parents=True, exist_ok=True)
        response = client.get(url)
        response.raise_for_status()
        temporary = path.with_name(f"{path.name}.part")
        try:
            temporary.write_bytes(response.content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        if self.pause_seconds:
            time.sleep(self.pause_seconds)
        return "downloaded"

    def tilejson(self, client: httpx.Client) -> dict[str, Any]:
        if self._tilejson is None:
            status = self._download_once(
                client, OPENFREEMAP_TILEJSON_URL, TILEJSON_PATH
            )
            payload = json.loads(TILEJSON_PATH.read_text(encoding="utf-8"))
            if not payload.get("tiles") or not payload.get("vector_layers"):
                raise RuntimeError("OpenFreeMap TileJSON lacks tiles/vector_layers")
            payload["_cache_status"] = status
            self._tilejson = payload
        return self._tilejson

    def _snapshot_id(self, template: str) -> str:
        prefix = template.split("/{z}", 1)[0].rstrip("/")
        return prefix.rsplit("/", 1)[-1]

    def _tile_path(self, template: str, zoom: int, x: int, y: int) -> Path:
        return (
            MODERN_GEOGRAPHY_RAW_DIR
            / self._snapshot_id(template)
            / str(zoom)
            / str(x)
            / f"{y}.pbf"
        )

    def _tile(
        self,
        client: httpx.Client,
        template: str,
        zoom: int,
        x: int,
        y: int,
    ) -> Path:
        path = self._tile_path(template, zoom, x, y)
        url = template.format(z=zoom, x=x, y=y)
        status = self._download_once(client, url, path)
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        self._touched_tiles[relative] = {
            "path": relative,
            "z": zoom,
            "x": x,
            "y": y,
            "source_url": url,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "cache_status": status,
        }
        return path

    def build_mosaic(
        self,
        coordinates: Iterable[tuple[float, float]],
        *,
        anchor_id: str,
        zoom: int,
        padding_tiles: int,
        origin_lon: float,
        origin_lat: float,
    ) -> WaterMosaic:
        points = list(coordinates)
        if not points:
            raise ValueError("cannot build a water mosaic without coordinates")
        tile_indexes = [lonlat_to_tile(lon, lat, zoom) for lon, lat in points]
        n = 2**zoom
        min_x = max(0, min(x for x, _ in tile_indexes) - padding_tiles)
        max_x = min(n - 1, max(x for x, _ in tile_indexes) + padding_tiles)
        min_y = max(0, min(y for _, y in tile_indexes) - padding_tiles)
        max_y = min(n - 1, max(y for _, y in tile_indexes) + padding_tiles)

        by_class: dict[str, list[BaseGeometry]] = {}
        with httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        ) as client:
            tilejson = self.tilejson(client)
            template = tilejson["tiles"][0]
            for x in range(min_x, max_x + 1):
                for y in range(min_y, max_y + 1):
                    path = self._tile(client, template, zoom, x, y)
                    decoded = mapbox_vector_tile.decode(
                        path.read_bytes(),
                        default_options={"transformer": _tile_transformer(x, y, zoom)},
                    )
                    layer = decoded.get("water")
                    if not layer:
                        continue
                    for feature in layer["features"]:
                        water_class = str(
                            feature.get("properties", {}).get("class") or "unknown"
                        )
                        geometry = shape(feature["geometry"])
                        if geometry.is_empty:
                            continue
                        if not geometry.is_valid:
                            geometry = make_valid(geometry)
                        by_class.setdefault(water_class, []).append(geometry)

        merged = {
            name: unary_union(geometries)
            for name, geometries in sorted(by_class.items())
        }
        marine = merged.pop("ocean", _empty_geometry())
        west, south, _, north = tile_bounds(min_x, max_y, zoom)
        _, _, east, _ = tile_bounds(max_x, min_y, zoom)
        source = {
            "dataset": "OpenFreeMap public vector tiles / OpenMapTiles water layer",
            "tilejson_url": OPENFREEMAP_TILEJSON_URL,
            "resolved_tile_template": template,
            "snapshot_id": self._snapshot_id(template),
            "tilejson_version": tilejson.get("version"),
            "tilejson_schema_version": tilejson.get("tilejson"),
            "analysis_zoom": zoom,
            "anchor_id": anchor_id,
            "tile_range": {
                "min_x": min_x,
                "max_x": max_x,
                "min_y": min_y,
                "max_y": max_y,
            },
            "geometry_crs": "EPSG:4326 after deterministic MVT/Web Mercator tile transform",
        }
        return WaterMosaic.from_geometries(
            marine=marine,
            inland_by_class=merged,
            coverage=box(west, south, east, north),
            reference_source=source,
            origin_lon=origin_lon,
            origin_lat=origin_lat,
        )

    def write_manifest(self) -> dict[str, Any]:
        tilejson = self._tilejson or read_json(TILEJSON_PATH)
        result = {
            "source": "OpenFreeMap public vector tiles",
            "tilejson_url": OPENFREEMAP_TILEJSON_URL,
            "resolved_tile_template": tilejson["tiles"][0],
            "snapshot_id": self._snapshot_id(tilejson["tiles"][0]),
            "tilejson": {
                "path": TILEJSON_PATH.relative_to(PROJECT_ROOT).as_posix(),
                "size_bytes": TILEJSON_PATH.stat().st_size,
                "sha256": sha256_file(TILEJSON_PATH),
            },
            "retrieved_or_verified_at_utc": utc_now(),
            "tile_count": len(self._touched_tiles),
            "tiles": [self._touched_tiles[key] for key in sorted(self._touched_tiles)],
            "raw_cache_policy": "download once; never overwrite an existing PBF",
        }
        write_json(SOURCE_MANIFEST_PATH, result)
        return result


def _valid_coordinate(lon: object, lat: object) -> bool:
    try:
        numeric_lon = float(lon)
        numeric_lat = float(lat)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(numeric_lon)
        and math.isfinite(numeric_lat)
        and -180 <= numeric_lon <= 180
        and -90 <= numeric_lat <= 90
    )


def _triage(
    water_kind: str | None,
    distance_to_land_km: float | None,
    config: PlausibilityConfig,
) -> str:
    if water_kind is None or distance_to_land_km is None:
        return "no_water_warning"
    if water_kind == "marine":
        if distance_to_land_km < config.nearshore_max_km:
            return "nearshore"
        if distance_to_land_km < config.moderate_offshore_max_km:
            return "moderate_offshore"
        return "far_offshore"
    if distance_to_land_km < config.nearshore_max_km:
        return "inland_near_boundary"
    if distance_to_land_km < config.moderate_offshore_max_km:
        return "inland_moderate_interior"
    return "inland_far_interior"


def classify_point(
    lon: object,
    lat: object,
    mosaic: WaterMosaic | None,
    *,
    config: PlausibilityConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    if not _valid_coordinate(lon, lat):
        return {
            "classification": "unknown",
            "reason": "invalid_coordinate",
            "distance_to_modern_land_km": None,
            "distance_to_modern_coastline_km": None,
            "reference_source": mosaic.reference_source if mosaic else None,
            "qa_interpretation": "unresolved",
        }
    if mosaic is None:
        return {
            "classification": "unknown",
            "reason": "geometry_unavailable",
            "distance_to_modern_land_km": None,
            "distance_to_modern_coastline_km": None,
            "reference_source": None,
            "qa_interpretation": "unresolved",
        }

    numeric_lon = float(lon)
    numeric_lat = float(lat)
    point = mosaic.point_km(numeric_lon, numeric_lat)
    marine_hit = not mosaic.marine_km.is_empty and mosaic.marine_km.covers(point)
    inland_classes = sorted(
        name
        for name, geometry in mosaic.inland_by_class_km.items()
        if not geometry.is_empty and geometry.covers(point)
    )
    water_kind = "marine" if marine_hit else "inland" if inland_classes else None
    containing_water = (
        mosaic.marine_km
        if marine_hit
        else unary_union([mosaic.inland_by_class_km[name] for name in inland_classes])
        if inland_classes
        else None
    )
    distance_to_land = (
        point.distance(containing_water.boundary)
        if containing_water is not None and not containing_water.is_empty
        else 0.0
    )
    distance_to_water = (
        0.0
        if water_kind
        else point.distance(mosaic.all_water_km)
        if not mosaic.all_water_km.is_empty
        else None
    )
    coastline_distance = (
        point.distance(mosaic.marine_km.boundary)
        if not mosaic.marine_km.is_empty
        else None
    )
    boundary_distance = distance_to_land if water_kind else distance_to_water
    boundary_uncertain = (
        boundary_distance is not None
        and boundary_distance <= config.boundary_uncertainty_km
    )
    if boundary_uncertain:
        classification = "boundary_uncertain"
    elif water_kind:
        classification = "modern_water"
    else:
        classification = "modern_land"

    water_type = (
        "modern_marine_water"
        if water_kind == "marine"
        else "modern_inland_water_unknown_origin"
        if water_kind == "inland"
        else None
    )
    return {
        "classification": classification,
        "water_membership": water_kind,
        "water_type": water_type,
        "water_classes": ["ocean"] if marine_hit else inland_classes,
        "distance_to_modern_land_km": round(distance_to_land, 3),
        "distance_to_modern_coastline_km": (
            round(coastline_distance, 3) if coastline_distance is not None else None
        ),
        "distance_to_nearest_mapped_water_km": (
            round(distance_to_water, 3) if distance_to_water is not None else None
        ),
        "triage": (
            "boundary_review"
            if boundary_uncertain
            else _triage(water_kind, distance_to_land, config)
        ),
        "thresholds_km": {
            "boundary_uncertainty": config.boundary_uncertainty_km,
            "nearshore_max": config.nearshore_max_km,
            "moderate_offshore_max": config.moderate_offshore_max_km,
            "meaning": "review priority only; never a historical correctness threshold",
        },
        "reference_source": mosaic.reference_source,
        "qa_interpretation": (
            "needs_review"
            if classification in {"modern_water", "boundary_uncertain"}
            else "no_modern_water_warning"
        ),
    }


def classify_feature(
    feature: dict[str, Any],
    mosaic: WaterMosaic | None,
    *,
    config: PlausibilityConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    coordinates = feature.get("geometry", {}).get("coordinates") or [None, None]
    return classify_point(coordinates[0], coordinates[1], mosaic, config=config)


def visual_dot_coordinate(
    lon: float,
    lat: float,
    *,
    config: PlausibilityConfig = DEFAULT_CONFIG,
) -> tuple[float, float]:
    world_pixels = config.maplibre_world_tile_size_px * 2 ** config.phase1_2_map_zoom
    longitude_offset = config.history_dot_center_offset_px / world_pixels * 360.0
    return lon + longitude_offset, lat


def deduplicate_occurrences(
    occurrences: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for occurrence in occurrences:
        grouped.setdefault(occurrence["tgaz_id"], []).append(occurrence)
    unique: list[dict[str, Any]] = []
    for tgaz_id, rows in sorted(grouped.items()):
        coordinates = sorted({(row["longitude"], row["latitude"]) for row in rows})
        classifications = sorted(
            {row["geometry_observation"]["classification"] for row in rows}
        )
        unique.append(
            {
                "tgaz_id": tgaz_id,
                "name": rows[0]["name"],
                "occurrence_count": len(rows),
                "occurrence_keys": sorted(row["occurrence_key"] for row in rows),
                "coordinates": [
                    {"longitude": lon, "latitude": lat} for lon, lat in coordinates
                ],
                "coordinate_consistent_across_occurrences": len(coordinates) == 1,
                "geometry_classifications": classifications,
            }
        )
    return unique


def _normalized_text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def load_v6_index(path: Path = V6_SHAPEFILE_PATH) -> dict[str, dict[str, Any]]:
    reader = shapefile.Reader(str(path), encoding="utf-8")
    records: dict[str, dict[str, Any]] = {}
    for shape_record in reader.iterShapeRecords():
        attributes = shape_record.record.as_dict()
        raw_id = attributes.get("SYS_ID")
        if raw_id in (None, "") or not shape_record.shape.points:
            continue
        numeric_id = str(raw_id).strip().removesuffix(".0")
        tgaz_id = numeric_id if numeric_id.startswith("hvd_") else f"hvd_{numeric_id}"
        lon, lat = shape_record.shape.points[0]
        records[tgaz_id] = {
            "tgaz_id": tgaz_id,
            "historical_instance_id": numeric_id,
            "name_simplified": _normalized_text(attributes.get("NAME_CH")),
            "name_traditional": _normalized_text(attributes.get("NAME_FT")),
            "feature_type": _normalized_text(attributes.get("TYPE_CH")),
            "valid_from": attributes.get("BEG_YR"),
            "valid_to": attributes.get("END_YR"),
            "present_location": _normalized_text(attributes.get("PRES_LOC")),
            "longitude": lon,
            "latitude": lat,
            "source": "CHGIS V6 Time Series County Points",
        }
    return records


def safe_v6_crosscheck(
    feature: dict[str, Any],
    v6_record: dict[str, Any] | None,
) -> dict[str, Any]:
    properties = feature.get("properties", {})
    tgaz_id = str(properties.get("tgaz_id") or feature.get("id") or "")
    if v6_record is None:
        return {
            "match_status": "no_exact_id_match",
            "match_confidence": "none",
            "reliable_match": False,
            "v6_coordinate": None,
            "distance_csv_to_v6_km": None,
        }

    checks = {
        "historical_instance_id": v6_record["tgaz_id"] == tgaz_id,
        "name_simplified": _normalized_text(properties.get("name"))
        == v6_record["name_simplified"],
        "valid_from": properties.get("valid_from") == v6_record["valid_from"],
        "valid_to": properties.get("valid_to") == v6_record["valid_to"],
        "feature_type": _normalized_text(properties.get("feature_type"))
        == v6_record["feature_type"],
    }
    reliable = all(checks.values())
    lon, lat = feature["geometry"]["coordinates"]
    distance_km = haversine(lat, lon, v6_record["latitude"], v6_record["longitude"])
    return {
        "match_status": (
            "exact_id_and_instance_match"
            if reliable
            else "exact_id_metadata_conflict"
        ),
        "match_confidence": "exact" if reliable else "insufficient",
        "reliable_match": reliable,
        "field_checks": checks,
        "v6_coordinate": {
            "longitude": v6_record["longitude"],
            "latitude": v6_record["latitude"],
        },
        "v6_metadata": {
            key: v6_record[key]
            for key in (
                "name_simplified",
                "name_traditional",
                "feature_type",
                "valid_from",
                "valid_to",
                "present_location",
                "source",
            )
        },
        "distance_csv_to_v6_km": round(distance_km, 3),
    }


def api_coordinate_crosscheck(
    feature: dict[str, Any], parsed_detail: dict[str, Any] | None
) -> dict[str, Any]:
    if not parsed_detail:
        return {
            "status": "api_detail_unavailable",
            "api_coordinate": None,
            "distance_csv_to_api_km": None,
            "coordinate_within_10m": None,
        }
    api_lat = parsed_detail.get("location", {}).get("lat")
    api_lon = parsed_detail.get("location", {}).get("lon")
    if not _valid_coordinate(api_lon, api_lat):
        return {
            "status": "api_coordinate_unavailable",
            "api_coordinate": None,
            "distance_csv_to_api_km": None,
            "coordinate_within_10m": None,
        }
    csv_lon, csv_lat = feature["geometry"]["coordinates"]
    distance_km = haversine(csv_lat, csv_lon, float(api_lat), float(api_lon))
    return {
        "status": "compared",
        "api_coordinate": {"longitude": api_lon, "latitude": api_lat},
        "distance_csv_to_api_km": round(distance_km, 6),
        "coordinate_within_10m": distance_km <= 0.01,
    }


def config_as_dict(config: PlausibilityConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    result = asdict(config)
    result["threshold_semantics"] = (
        "review prioritization only; not a historical truth or error threshold"
    )
    return result
