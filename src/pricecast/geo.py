"""Spatial helpers: where a market is, and which markets are near a farmer.

Distances are great-circle (haversine) scaled by a road-circuity factor. That
is deliberately conservative: a real OSRM/Google routing call is a drop-in
replacement behind `road_distance_km`, but a hackathon deployment should not
depend on a paid API for the number that anchors the netback estimate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import registry
from .names import canonical_county, canonical_market

# Kenyan trunk/rural network: road distance typically exceeds straight line by
# 20-35%. 1.30 is the midpoint used by transport-cost literature for East Africa.
CIRCUITY_FACTOR = 1.30


@dataclass(frozen=True)
class Place:
    name: str
    county: str
    lat: float
    lon: float
    verified: bool = False
    kind: str = "market"      # market | county_centroid


@dataclass(frozen=True)
class MarketDistance:
    market: str
    county: str
    straight_km: float
    road_km: float
    precision: str            # 'market' | 'county_centroid'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def road_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Estimated road distance. Swap for a routing API without touching callers."""
    return haversine_km(lat1, lon1, lat2, lon2) * CIRCUITY_FACTOR


def locate_market(county: object, market: object) -> Place | None:
    """Exact market coordinates, else the county centroid, else None."""
    cty, mkt = canonical_county(county), canonical_market(market)
    row = registry.markets_geo().get((cty.lower(), mkt.lower()))
    if row:
        return Place(row["market"], row["county"], row["lat"], row["lon"],
                     row["verified"], "market")
    return locate_county(cty)


def locate_county(county: object) -> Place | None:
    cty = canonical_county(county)
    row = registry.county_centroids().get(cty.lower())
    if not row:
        return None
    return Place(row["county"], row["county"], row["lat"], row["lon"], False, "county_centroid")


def distance_between(origin: Place | None, dest: Place | None) -> MarketDistance | None:
    if origin is None or dest is None:
        return None
    straight = haversine_km(origin.lat, origin.lon, dest.lat, dest.lon)
    precision = "market" if dest.kind == "market" else "county_centroid"
    return MarketDistance(dest.name, dest.county, round(straight, 1),
                          round(straight * CIRCUITY_FACTOR, 1), precision)


def nearest_markets(
    origin_county: object,
    candidates: list[tuple[str, str]],
    limit: int = 5,
) -> list[MarketDistance]:
    """Rank `candidates` [(county, market), ...] by distance from a county centroid.

    Candidates without coordinates fall back to their own county centroid, and
    are reported with precision='county_centroid' so the UI can hedge the number
    instead of pretending to a precision it does not have.
    """
    origin = locate_county(origin_county)
    if origin is None:
        return []
    out: list[MarketDistance] = []
    seen: set[tuple[str, str]] = set()
    for county, market in candidates:
        key = (canonical_county(county).lower(), canonical_market(market).lower())
        if key in seen:
            continue
        seen.add(key)
        dest = locate_market(county, market)
        if dest is None:
            continue
        dist = distance_between(origin, dest)
        if dist is None:
            continue
        out.append(MarketDistance(canonical_market(market), canonical_county(county),
                                  dist.straight_km, dist.road_km, dist.precision))
    out.sort(key=lambda d: d.road_km)
    return out[:limit]


def coverage_stats(candidates: list[tuple[str, str]]) -> dict:
    """How much of the observed market list has real coordinates (honesty metric)."""
    total = exact = 0
    for county, market in {(canonical_county(c), canonical_market(m)) for c, m in candidates}:
        total += 1
        if registry.markets_geo().get((county.lower(), market.lower())):
            exact += 1
    return {
        "markets": total,
        "with_coordinates": exact,
        "pct": round(100 * exact / total, 1) if total else 0.0,
    }
