from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

from .temporal import valid_for


EARTH_RADIUS_KM = 6371.0088


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def inside_bbox(
    anchor_lat: float,
    anchor_lon: float,
    candidate_lat: float,
    candidate_lon: float,
    radius_km: float,
) -> bool:
    latitude_delta = radius_km / 110.574
    cosine = abs(math.cos(math.radians(anchor_lat)))
    longitude_delta = (
        180.0 if cosine < 1e-12 else min(180.0, radius_km / (111.320 * cosine))
    )
    wrapped_lon_delta = abs((candidate_lon - anchor_lon + 180.0) % 360.0 - 180.0)
    return (
        abs(candidate_lat - anchor_lat) <= latitude_delta
        and wrapped_lon_delta <= longitude_delta
    )


def query_nearby(
    rows: Iterable[dict[str, Any]],
    *,
    anchor_lat: float,
    anchor_lon: float,
    year: int,
    radius_km: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for row in rows:
        if not valid_for(row.get("valid_from"), row.get("valid_to"), year):
            continue
        lat, lon = row.get("lat"), row.get("lon")
        if lat is None or lon is None:
            continue
        if not inside_bbox(anchor_lat, anchor_lon, lat, lon, radius_km):
            continue
        distance_km = haversine(anchor_lat, anchor_lon, lat, lon)
        if distance_km > radius_km:
            continue
        feature = dict(row)
        feature.update(
            {
                "distance_km": round(distance_km, 3),
                "relation_to_anchor": "spatial_nearby",
                "lineage_claim": None,
            }
        )
        results.append(feature)
    return sorted(results, key=lambda item: (item["distance_km"], item["tgaz_id"]))
