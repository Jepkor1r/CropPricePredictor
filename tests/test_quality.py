"""Plausibility screening — real KAMIS typos must never reach a farmer."""
from __future__ import annotations

import pandas as pd

from helpers import make_observation
from pricecast import db as DB
from pricecast import prices, quality


def _onion_frame(extra: list[dict]) -> pd.DataFrame:
    """A realistic Dry Onions body at ~50 KES/kg plus whatever is passed in."""
    rows = [
        make_observation(
            commodity="Dry Onions", classification="-", market=f"Market {i}",
            county="Nakuru", date=f"2021-10-{(i % 28) + 1:02d}",
            wholesale_price=50.0, wholesale_per_kg=50.0,
            retail_price=None, retail_per_kg=None,
        )
        for i in range(40)
    ]
    return pd.DataFrame(rows + extra)


def test_absurdly_low_price_is_flagged():
    """Gakoromone, Meru 2021-12-03 really is 0.02 KES/kg in the export."""
    df = _onion_frame([make_observation(
        commodity="Dry Onions", classification="-", market="Gakoromone", county="Meru",
        date="2021-12-03", wholesale_price=0.02, wholesale_per_kg=0.02,
        retail_price=None, retail_per_kg=None,
    )])
    flags, reasons = quality.flag_implausible(df)
    assert flags.iloc[-1] == 1
    assert "data entry error" in reasons.iloc[-1]


def test_absurdly_high_price_is_flagged():
    """Sibanga, Trans Nzoia 2021-12-31 really is 2100 KES/kg in the export."""
    df = _onion_frame([make_observation(
        commodity="Dry Onions", classification="-", market="Sibanga", county="Trans Nzoia",
        date="2021-12-31", wholesale_price=2100.0, wholesale_per_kg=2100.0,
        retail_price=None, retail_per_kg=None,
    )])
    flags, reasons = quality.flag_implausible(df)
    assert flags.iloc[-1] == 1
    assert "typical price" in reasons.iloc[-1]


def test_ordinary_variation_is_not_flagged():
    df = _onion_frame([make_observation(
        commodity="Dry Onions", classification="-", market="Kongowea", county="Mombasa",
        date="2021-11-15", wholesale_price=140.0, wholesale_per_kg=140.0,
        retail_price=None, retail_per_kg=None,
    )])
    flags, _ = quality.flag_implausible(df)
    assert flags.iloc[-1] == 0
    assert flags.sum() == 0


def test_price_inflation_across_eras_is_not_flagged():
    """Onions at 30 in 2005 and 62 in 2021 are both legitimate."""
    old = [make_observation(
        commodity="Dry Onions", classification="-", market=f"Old {i}", county="Nakuru",
        date=f"2005-06-{(i % 28) + 1:02d}", wholesale_price=30.0, wholesale_per_kg=30.0,
        retail_price=None, retail_per_kg=None,
    ) for i in range(25)]
    df = pd.concat([_onion_frame([]), pd.DataFrame(old)], ignore_index=True)
    flags, _ = quality.flag_implausible(df)
    assert flags.sum() == 0


def test_flagged_rows_are_kept_but_hidden(conn):
    """Auditable, not deleted: still in the table, absent from the product."""
    df = _onion_frame([make_observation(
        commodity="Dry Onions", classification="-", market="Sibanga", county="Trans Nzoia",
        date=str(pd.Timestamp.today().normalize().date()),
        wholesale_price=2100.0, wholesale_per_kg=2100.0,
        retail_price=None, retail_per_kg=None,
    )])
    flags, reasons = quality.flag_implausible(df)
    df["quality_flag"], df["quality_reason"] = flags, reasons
    DB.upsert_observations(conn, df)

    assert len(DB.read_observations(conn, include_flagged=True)) == len(df)
    assert len(DB.read_observations(conn)) == len(df) - 1

    served = prices.latest_prices(conn, "Dry Onions", max_age_days=10_000)
    assert "Sibanga" not in set(served["market"])


def test_screening_summary_reports_what_was_removed():
    df = _onion_frame([make_observation(
        commodity="Dry Onions", classification="-", market="Sibanga", county="Trans Nzoia",
        date="2021-12-31", wholesale_price=2100.0, wholesale_per_kg=2100.0,
        retail_price=None, retail_per_kg=None,
    )])
    flags, reasons = quality.flag_implausible(df)
    df["quality_flag"], df["quality_reason"] = flags, reasons
    summary = quality.screening_summary(df)
    assert summary.iloc[0]["flagged_rows"] == 1
    assert summary.iloc[0]["commodity"] == "Dry Onions"
