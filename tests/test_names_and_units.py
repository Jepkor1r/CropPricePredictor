"""Canonicalisation and unit conversion — the two places a silent data bug hides."""
from __future__ import annotations

import pytest

from pricecast import units
from pricecast.ingest import parse_price
from pricecast.names import canonical_county, canonical_market, is_junk_market, squash


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Uasin-Gishu", "Uasin Gishu"),
        ("uasin gishu", "Uasin Gishu"),
        ("Homa-bay", "Homa Bay"),
        ("Trans-Nzoia", "Trans Nzoia"),
        ("Muranga", "Murang'a"),
        ("Taita-Taveta", "Taita Taveta"),
        ("Elgeyo-Marakwet", "Elgeyo Marakwet"),
        ("  NAIROBI  ", "Nairobi"),
        ("", ""),
    ],
)
def test_canonical_county(raw, expected):
    assert canonical_county(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Kajiado Market", "Kajiado"),
        ("Kimana Crops market", "Kimana Crops"),
        ("Bomet  Market", "Bomet"),
        ("Nairobi Wakulima", "Nairobi Wakulima"),
        ("Market", "Market"),          # never blank out a name entirely
    ],
)
def test_canonical_market(raw, expected):
    assert canonical_market(raw) == expected


def test_market_alias_table_overrides_rule():
    aliases = {"Kibuye": "Kisumu Kibuye"}
    assert canonical_market("Kibuye", aliases) == "Kisumu Kibuye"


def test_junk_rows_are_identified():
    assert is_junk_market("test market", "", {"test market"})
    assert is_junk_market("Eldoret Main", "", {"test market"})   # missing county
    assert not is_junk_market("Eldoret Main", "Uasin Gishu", {"test market"})


def test_squash_handles_nan_like_values():
    assert squash("nan") == ""
    assert squash(None) == ""
    assert squash("  Mixed-Traditional  ") == "Mixed-Traditional"


@pytest.mark.parametrize(
    ("cell", "value", "unit"),
    [
        ("38.89/Kg", 38.89, "Kg"),
        ("38.89/kg", 38.89, "Kg"),        # case variant seen in onions-final.xls
        ("1,250/Bag", 1250.0, "Bag"),
        ("3,200 / 90kg bag", 3200.0, "Bag"),
        (" - ", None, None),
        ("-", None, None),
        ("", None, None),
        (None, None, None),
    ],
)
def test_parse_price(cell, value, unit):
    assert parse_price(cell) == (value, unit)


def test_kg_prices_pass_through():
    conversion = units.to_per_kg(50.0, "Kg", "Dry Maize")
    assert conversion.ok
    assert conversion.price_per_kg == 50.0
    assert conversion.reason == "already_kg"


def test_bag_price_is_converted_not_dropped():
    conversion = units.to_per_kg(4500.0, "Bag", "Dry Maize")
    assert conversion.ok
    assert conversion.kg_equivalent == 90
    assert conversion.price_per_kg == pytest.approx(50.0)


def test_potato_bag_is_50kg_not_90():
    """The extended-bag dispute is the whole point; the registry must encode it."""
    standard = units.to_per_kg(2500.0, "Bag", "Red Irish potato")
    extended = units.to_per_kg(2500.0, "Extended Bag", "Red Irish potato")
    assert standard.kg_equivalent == 50
    assert extended.kg_equivalent == 110
    assert standard.price_per_kg > extended.price_per_kg


def test_unknown_packaging_reports_a_reason():
    conversion = units.to_per_kg(100.0, "Crate", "Nonexistent Crop")
    assert not conversion.ok
    assert "packaging.csv" in conversion.reason


def test_litre_is_not_forced_to_mass():
    conversion = units.to_per_kg(60.0, "Litre", "Cow Milk(At collection point)")
    assert not conversion.ok
    assert conversion.basis == "volume"
