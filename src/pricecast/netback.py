"""Farm-gate floor estimation (net-back pricing).

    floor = wholesale - transport - cess - handling - spoilage

Design rule: **never emit a single fake-precise number.** Every deduction is a
low/high range with a cited source, and the output is a band. A broker will
reject a made-up "KES 43.20" instantly and the farmer loses trust in the
service; a defensible "your floor is 41-45, here is the arithmetic" survives the
argument at the farm gate.

Deliberate modelling choices:
  * Transport rates are *hire* rates, so they already include the transporter's
    margin. No separate margin line, which would double-count it.
  * Rates are diesel-indexed off the EPRA monthly price: only the fuel share of
    operating cost moves with the pump price (CAK 2019: ~38%).
  * Distance is road-estimated (haversine x circuity). Swapping in OSRM changes
    one function in geo.py and nothing here.
  * Cess is charged twice in practice - leaving the producing county and
    entering the terminal market - so both are modelled, and both are flagged
    INDICATIVE until a pilot county's Finance Act is digitised.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import geo, registry
from .config import (
    FUEL_SHARE_OF_TRUCK_COST,
    HANDLING_PCT_HIGH,
    HANDLING_PCT_LOW,
    UTILISATION_HIGH,
    UTILISATION_LOW,
)
from .names import canonical_county, canonical_market


@dataclass(frozen=True)
class Component:
    name: str
    low: float
    high: float
    source: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NetbackEstimate:
    commodity: str
    origin_county: str
    market: str
    market_county: str
    wholesale_kes_per_kg: float
    floor_low: float
    floor_high: float
    distance_km: float | None
    distance_precision: str
    vehicle_class: str
    diesel_label: str
    components: list[Component] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_deductions_low(self) -> float:
        return round(sum(c.low for c in self.components), 2)

    @property
    def total_deductions_high(self) -> float:
        return round(sum(c.high for c in self.components), 2)

    @property
    def share_of_wholesale(self) -> float:
        """Mid-point deductions as a share of the wholesale price."""
        if not self.wholesale_kes_per_kg:
            return 0.0
        mid = (self.total_deductions_low + self.total_deductions_high) / 2
        return round(100 * mid / self.wholesale_kes_per_kg, 1)

    def to_dict(self) -> dict:
        return {
            "commodity": self.commodity,
            "origin_county": self.origin_county,
            "market": self.market,
            "market_county": self.market_county,
            "wholesale_kes_per_kg": self.wholesale_kes_per_kg,
            "floor_low": self.floor_low,
            "floor_high": self.floor_high,
            "distance_km": self.distance_km,
            "distance_precision": self.distance_precision,
            "vehicle_class": self.vehicle_class,
            "diesel": self.diesel_label,
            "deductions_low": self.total_deductions_low,
            "deductions_high": self.total_deductions_high,
            "deductions_pct_of_wholesale": self.share_of_wholesale,
            "components": [c.to_dict() for c in self.components],
            "warnings": self.warnings,
        }

    def summary_line(self) -> str:
        return (
            f"Farm-gate floor {self.floor_low:.0f}-{self.floor_high:.0f} KES/kg "
            f"(wholesale {self.wholesale_kes_per_kg:.0f} less "
            f"{self.total_deductions_low:.0f}-{self.total_deductions_high:.0f} costs)"
        )


def _cess_row(county: str) -> dict:
    table = registry.cess()
    return table.get(canonical_county(county).lower()) or table.get("_default") or {
        "kes_per_bag_low": 0.0, "kes_per_bag_high": 0.0, "bag_kg": 90.0,
        "source": "no cess data", "county": county, "effective_year": "",
    }


def _spoilage_row(commodity: str) -> dict:
    cluster = registry.commodity_clusters().get(commodity.strip().lower(), "_default")
    table = registry.spoilage()
    return table.get(cluster.lower()) or table.get("_default") or {
        "pct_low": 0.0, "pct_high": 0.0, "source": "no spoilage data",
    }


def choose_vehicle(consignment_kg: float | None) -> dict:
    rates = registry.transport_rates()
    if not rates:
        return {
            "vehicle_class": "lorry_7t", "capacity_kg": 7000.0,
            "kes_per_km_low": 100.0, "kes_per_km_high": 140.0,
            "ref_diesel_kes_per_litre": 165.0, "source": "built-in default",
        }
    if consignment_kg:
        for rate in rates:
            if rate["capacity_kg"] >= consignment_kg:
                return rate
        return rates[-1]
    mid = [r for r in rates if r["vehicle_class"].startswith("lorry_7")]
    return mid[0] if mid else rates[len(rates) // 2]


def diesel_index(ref_price: float) -> tuple[float, str]:
    """Scale factor applied to the rate card for today's pump price."""
    current, label = registry.latest_diesel_price()
    if not ref_price:
        return 1.0, label
    return 1 + FUEL_SHARE_OF_TRUCK_COST * (current / ref_price - 1), label


def estimate(
    commodity: str,
    wholesale_kes_per_kg: float,
    origin_county: str,
    market: str,
    market_county: str,
    consignment_kg: float | None = None,
) -> NetbackEstimate:
    origin_county = canonical_county(origin_county)
    market_county = canonical_county(market_county)
    market = canonical_market(market)
    warnings: list[str] = []

    # --- distance -----------------------------------------------------------
    origin = geo.locate_county(origin_county)
    dest = geo.locate_market(market_county, market)
    dist = geo.distance_between(origin, dest)
    if dist is None:
        distance_km, precision = None, "unknown"
        warnings.append(
            "No coordinates for this origin/market pair - transport cost omitted."
        )
    else:
        distance_km, precision = dist.road_km, dist.precision
        if precision != "market":
            warnings.append(
                "Market coordinates not on file; distance measured to the county centre."
            )
        if origin and dest and origin.kind == "county_centroid":
            warnings.append("Distance is from the county centre, not your exact farm.")

    # --- transport ----------------------------------------------------------
    components: list[Component] = []
    vehicle = choose_vehicle(consignment_kg)
    index, diesel_label = diesel_index(vehicle["ref_diesel_kes_per_litre"])
    if distance_km:
        low = vehicle["kes_per_km_low"] * index * distance_km / (
            vehicle["capacity_kg"] * UTILISATION_HIGH
        )
        high = vehicle["kes_per_km_high"] * index * distance_km / (
            vehicle["capacity_kg"] * UTILISATION_LOW
        )
        components.append(Component(
            name="transport",
            low=round(low, 2), high=round(high, 2),
            source=vehicle["source"],
            detail=(
                f"{distance_km:.0f} km by {vehicle['vehicle_class']} at "
                f"{vehicle['kes_per_km_low']:.0f}-{vehicle['kes_per_km_high']:.0f} KES/km "
                f"x{index:.2f} diesel index ({diesel_label}), "
                f"{int(UTILISATION_LOW * 100)}-{int(UTILISATION_HIGH * 100)}% payload"
            ),
        ))
    else:
        diesel_label = registry.latest_diesel_price()[1]

    # --- cess (origin county, then terminal market county) ------------------
    for label, county in (("cess (origin county)", origin_county),
                          ("cess/levy (market county)", market_county)):
        row = _cess_row(county)
        bag_kg = row.get("bag_kg") or 90.0
        low = (row["kes_per_bag_low"] or 0.0) / bag_kg
        high = (row["kes_per_bag_high"] or 0.0) / bag_kg
        if high <= 0:
            continue
        components.append(Component(
            name=f"{label}: {county}",
            low=round(low, 2), high=round(high, 2),
            source=row.get("source", ""),
            detail=(
                f"KES {row['kes_per_bag_low']:.0f}-{row['kes_per_bag_high']:.0f} "
                f"per {bag_kg:.0f}kg bag, {row.get('effective_year', '')}"
            ),
        ))
        if "INDICATIVE" in (row.get("source") or ""):
            warnings.append(f"Cess rate for {county} is indicative - verify the Finance Act.")

    # --- handling and brokerage --------------------------------------------
    components.append(Component(
        name="handling & market brokerage",
        low=round(wholesale_kes_per_kg * HANDLING_PCT_LOW, 2),
        high=round(wholesale_kes_per_kg * HANDLING_PCT_HIGH, 2),
        source="Tegemeo TR31 marketing-cost structure (loading, offloading, market broker)",
        detail=f"{HANDLING_PCT_LOW:.0%}-{HANDLING_PCT_HIGH:.0%} of wholesale",
    ))

    # --- spoilage -----------------------------------------------------------
    spoil = _spoilage_row(commodity)
    if spoil["pct_high"] > 0:
        components.append(Component(
            name="spoilage in transit",
            low=round(wholesale_kes_per_kg * spoil["pct_low"], 2),
            high=round(wholesale_kes_per_kg * spoil["pct_high"], 2),
            source=spoil.get("source", ""),
            detail=f"{spoil['pct_low']:.0%}-{spoil['pct_high']:.0%} of consignment value",
        ))

    total_low = sum(c.low for c in components)
    total_high = sum(c.high for c in components)
    floor_high = wholesale_kes_per_kg - total_low
    floor_low = wholesale_kes_per_kg - total_high
    if floor_low < 0:
        warnings.append(
            "Estimated costs exceed the wholesale price - this route is uneconomic "
            "at today's price; consider a nearer market."
        )
        floor_low = 0.0
    floor_high = max(floor_high, floor_low)

    return NetbackEstimate(
        commodity=commodity,
        origin_county=origin_county,
        market=market,
        market_county=market_county,
        wholesale_kes_per_kg=round(wholesale_kes_per_kg, 2),
        floor_low=round(floor_low, 2),
        floor_high=round(floor_high, 2),
        distance_km=distance_km,
        distance_precision=precision,
        vehicle_class=vehicle["vehicle_class"],
        diesel_label=diesel_label,
        components=components,
        warnings=warnings,
    )
