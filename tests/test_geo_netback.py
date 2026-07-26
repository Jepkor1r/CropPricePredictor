"""Geo lookups and the netback arithmetic that anchors the farm-gate floor."""
from __future__ import annotations

import pytest

from pricecast import geo, netback, registry


def test_haversine_known_distance():
    """Eldoret to Nairobi is ~265 km straight line."""
    eldoret = geo.locate_market("Uasin Gishu", "Eldoret Main")
    nairobi = geo.locate_market("Nairobi", "Nairobi Wakulima")
    straight = geo.haversine_km(eldoret.lat, eldoret.lon, nairobi.lat, nairobi.lon)
    assert 250 < straight < 285


def test_road_distance_exceeds_straight_line():
    assert geo.road_distance_km(0, 36, 1, 36) > geo.haversine_km(0, 36, 1, 36)


def test_market_suffix_and_county_variants_resolve():
    assert geo.locate_market("Uasin-Gishu", "Eldoret Main") is not None
    assert geo.locate_market("Kajiado", "Kajiado Market").kind == "market"


def test_unknown_market_falls_back_to_county_centroid():
    place = geo.locate_market("Nakuru", "Some Unlisted Market")
    assert place is not None
    assert place.kind == "county_centroid"


def test_unknown_county_returns_none():
    assert geo.locate_market("Atlantis", "Nowhere") is None


def test_nearest_markets_are_ordered_by_distance():
    candidates = [
        ("Nairobi", "Nairobi Wakulima"),
        ("Uasin Gishu", "Eldoret Main"),
        ("Trans Nzoia", "Kitale Municipality"),
    ]
    ranked = geo.nearest_markets("Uasin Gishu", candidates, limit=3)
    assert [r.market for r in ranked][:2] == ["Eldoret Main", "Kitale Municipality"]
    assert ranked[0].road_km < ranked[-1].road_km


def test_nearest_markets_deduplicates():
    candidates = [("Nairobi", "Nairobi Wakulima")] * 5
    assert len(geo.nearest_markets("Nakuru", candidates, limit=5)) == 1


# --- netback ---------------------------------------------------------------

def test_floor_is_a_band_below_wholesale():
    estimate = netback.estimate(
        "Dry Maize", wholesale_kes_per_kg=50.0, origin_county="Trans Nzoia",
        market="Nairobi Wakulima", market_county="Nairobi",
    )
    assert 0 < estimate.floor_low <= estimate.floor_high < 50.0
    assert estimate.components, "every deduction must be itemised"
    assert all(c.source for c in estimate.components), "every line needs a citation"


def test_longer_haul_means_a_lower_floor():
    near = netback.estimate("Dry Maize", 50.0, "Nakuru", "Nairobi Wakulima", "Nairobi")
    far = netback.estimate("Dry Maize", 50.0, "Trans Nzoia", "Nairobi Wakulima", "Nairobi")
    assert far.floor_low < near.floor_low


def test_perishable_crop_loses_more_than_a_cereal():
    maize = netback.estimate("Dry Maize", 50.0, "Nakuru", "Nairobi Wakulima", "Nairobi")
    tomato = netback.estimate("Tomatoes", 50.0, "Nakuru", "Nairobi Wakulima", "Nairobi")
    assert tomato.floor_low < maize.floor_low


def test_transport_is_indexed_to_the_epra_diesel_price():
    index_at_reference, _ = netback.diesel_index(registry.latest_diesel_price()[0])
    assert index_at_reference == pytest.approx(1.0)
    doubled = netback.diesel_index(registry.latest_diesel_price()[0] / 2)[0]
    assert doubled > 1.0


def test_transport_matches_the_tegemeo_benchmark_order_of_magnitude():
    """Tegemeo TR31: onions Naroosura->Nairobi, 260 km, ~KES 2.5/kg in the 2000s.

    Escalated to today's diesel that is roughly 4-9 KES/kg for a 7t lorry; the
    model must land in that band or the rate card is wrong.
    """
    vehicle = netback.choose_vehicle(None)
    index, _ = netback.diesel_index(vehicle["ref_diesel_kes_per_litre"])
    low = vehicle["kes_per_km_low"] * index * 260 / (vehicle["capacity_kg"] * 0.9)
    high = vehicle["kes_per_km_high"] * index * 260 / (vehicle["capacity_kg"] * 0.6)
    assert 3.0 < low < 6.0
    assert 6.0 < high < 12.0


def test_vehicle_choice_scales_with_consignment():
    assert netback.choose_vehicle(500)["vehicle_class"] == "pickup_3t"
    assert netback.choose_vehicle(12000)["vehicle_class"] == "lorry_15t"


def test_uneconomic_route_is_flagged_not_negative():
    estimate = netback.estimate(
        "Tomatoes", wholesale_kes_per_kg=2.0, origin_county="Turkana",
        market="Nairobi Wakulima", market_county="Nairobi",
    )
    assert estimate.floor_low == 0.0
    assert any("uneconomic" in w for w in estimate.warnings)


def test_missing_geography_warns_and_omits_transport():
    estimate = netback.estimate(
        "Dry Maize", 50.0, "Atlantis", "Nairobi Wakulima", "Nairobi"
    )
    assert estimate.distance_km is None
    assert not any(c.name == "transport" for c in estimate.components)
    assert estimate.warnings


def test_indicative_cess_is_disclosed():
    estimate = netback.estimate("Dry Maize", 50.0, "Nakuru", "Nairobi Wakulima", "Nairobi")
    assert any("indicative" in w.lower() for w in estimate.warnings)


def test_marginal_route_is_called_out_when_costs_dominate():
    """Real case: cabbages at 10 KES/kg, 91 km haul - costs are ~55% of the price."""
    estimate = netback.estimate(
        "Cabbages", wholesale_kes_per_kg=10.0, origin_county="Nyandarua",
        market="Kagio", market_county="Kirinyaga",
    )
    assert estimate.floor_low > 0
    assert estimate.share_of_wholesale > netback.MARGINAL_ROUTE_COST_SHARE
    assert any("nearer market or holding" in w for w in estimate.warnings)


def test_healthy_route_gets_no_marginal_warning():
    estimate = netback.estimate(
        "Dry Maize", wholesale_kes_per_kg=50.0, origin_county="Nakuru",
        market="Nairobi Wakulima", market_county="Nairobi",
    )
    assert not any("nearer market or holding" in w for w in estimate.warnings)
