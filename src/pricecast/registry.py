"""Loaders for the static reference registries in data/registry/.

These CSVs are the auditable, human-editable inputs the netback engine and the
geo layer depend on. Every row carries a `source` column so any number shown to
a farmer can be traced back to a citation.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from .config import DEFAULT_DIESEL_KES_PER_LITRE, REGISTRY_DIR


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get(next(iter(row)))]


def _f(row: dict, key: str, default: float | None = None) -> float | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def units() -> dict[str, dict]:
    """unit_raw (lowercased) -> {canonical, kg_equivalent|None, basis}."""
    out = {}
    for row in _read(REGISTRY_DIR / "units.csv"):
        out[row["unit_raw"].strip().lower()] = {
            "canonical": row["canonical"].strip(),
            "kg_equivalent": _f(row, "kg_equivalent"),
            "basis": (row.get("basis") or "mass").strip(),
        }
    return out


@lru_cache(maxsize=1)
def packaging() -> dict[tuple[str, str], dict]:
    """(commodity.lower(), canonical unit.lower()) -> {kg_equivalent, source}."""
    out = {}
    for row in _read(REGISTRY_DIR / "packaging.csv"):
        key = (row["commodity"].strip().lower(), row["unit"].strip().lower())
        out[key] = {"kg_equivalent": _f(row, "kg_equivalent"), "source": row.get("source", "")}
    return out


@lru_cache(maxsize=1)
def markets_geo() -> dict[tuple[str, str], dict]:
    """(county.lower(), market.lower()) -> {lat, lon, verified, source}."""
    out = {}
    for row in _read(REGISTRY_DIR / "markets_geo.csv"):
        lat, lon = _f(row, "lat"), _f(row, "lon")
        if lat is None or lon is None:
            continue
        out[(row["county"].strip().lower(), row["market"].strip().lower())] = {
            "county": row["county"].strip(),
            "market": row["market"].strip(),
            "lat": lat,
            "lon": lon,
            "verified": (row.get("verified") or "").strip().lower() in {"1", "true", "yes"},
            "source": row.get("source", ""),
        }
    return out


@lru_cache(maxsize=1)
def county_centroids() -> dict[str, dict]:
    out = {}
    for row in _read(REGISTRY_DIR / "county_centroids.csv"):
        lat, lon = _f(row, "lat"), _f(row, "lon")
        if lat is None or lon is None:
            continue
        out[row["county"].strip().lower()] = {
            "county": row["county"].strip(), "lat": lat, "lon": lon,
        }
    return out


@lru_cache(maxsize=1)
def transport_rates() -> list[dict]:
    rows = []
    for row in _read(REGISTRY_DIR / "transport_rates.csv"):
        rows.append({
            "vehicle_class": row["vehicle_class"].strip(),
            "capacity_kg": _f(row, "capacity_kg", 0.0),
            "kes_per_km_low": _f(row, "kes_per_km_low", 0.0),
            "kes_per_km_high": _f(row, "kes_per_km_high", 0.0),
            "ref_diesel_kes_per_litre": _f(
                row, "ref_diesel_kes_per_litre", DEFAULT_DIESEL_KES_PER_LITRE
            ),
            "source": row.get("source", ""),
        })
    return sorted(rows, key=lambda r: r["capacity_kg"])


@lru_cache(maxsize=1)
def cess() -> dict[str, dict]:
    """county.lower() -> cess rate expressed per 90kg-equivalent bag."""
    out = {}
    for row in _read(REGISTRY_DIR / "cess.csv"):
        out[row["county"].strip().lower()] = {
            "county": row["county"].strip(),
            "kes_per_bag_low": _f(row, "kes_per_bag_low", 0.0),
            "kes_per_bag_high": _f(row, "kes_per_bag_high", 0.0),
            "bag_kg": _f(row, "bag_kg", 90.0),
            "effective_year": (row.get("effective_year") or "").strip(),
            "source": row.get("source", ""),
        }
    return out


@lru_cache(maxsize=1)
def spoilage() -> dict[str, dict]:
    """cluster -> {pct_low, pct_high} share of consignment value lost in transit."""
    out = {}
    for row in _read(REGISTRY_DIR / "spoilage.csv"):
        out[row["cluster"].strip().lower()] = {
            "pct_low": _f(row, "pct_low", 0.0),
            "pct_high": _f(row, "pct_high", 0.0),
            "source": row.get("source", ""),
        }
    return out


@lru_cache(maxsize=1)
def commodity_clusters() -> dict[str, str]:
    out = {}
    for row in _read(REGISTRY_DIR / "commodity_clusters.csv"):
        out[row["commodity"].strip().lower()] = row["cluster"].strip()
    return out


def latest_diesel_price() -> tuple[float, str]:
    """Most recent EPRA diesel price on file -> (kes_per_litre, label)."""
    rows = _read(REGISTRY_DIR / "fuel_prices.csv")
    rows = [r for r in rows if _f(r, "diesel_kes_per_litre") is not None]
    if not rows:
        return DEFAULT_DIESEL_KES_PER_LITRE, "default (no EPRA data on file)"
    latest = max(rows, key=lambda r: r["effective_month"])
    return (
        _f(latest, "diesel_kes_per_litre", DEFAULT_DIESEL_KES_PER_LITRE),
        f"EPRA {latest['effective_month']}",
    )


def reset_cache() -> None:
    """Drop memoised registries (used by tests that write temp registries)."""
    for fn in (
        units, packaging, markets_geo, county_centroids, transport_rates,
        cess, spoilage, commodity_clusters,
    ):
        fn.cache_clear()
