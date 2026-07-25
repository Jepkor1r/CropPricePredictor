"""Fixtures data builders shared across the test modules."""
from __future__ import annotations

import pandas as pd


def make_observation(**overrides) -> dict:
    row = {
        "commodity": "Dry Maize",
        "classification": "White Maize",
        "grade": "-",
        "sex": "-",
        "market": "Eldoret Main",
        "county": "Uasin Gishu",
        "date": "2026-07-20",
        "wholesale_price": 50.0,
        "retail_price": 60.0,
        "price_unit": "Kg",
        "wholesale_per_kg": 50.0,
        "retail_per_kg": 60.0,
        "kg_per_unit": 1.0,
        "unit_basis": "mass",
        "supply_volume": 1000.0,
        "n_reports": 1,
        "source_file": "test.xls",
    }
    row.update(overrides)
    return row


def weekly_series(
    n_weeks: int = 40,
    start: str = "2026-01-05",
    price: float = 50.0,
    **keys,
) -> pd.DataFrame:
    """A clean weekly observation frame for one series."""
    base = {
        "commodity": "Dry Maize", "classification": "White Maize", "grade": "-",
        "sex": "-", "market": "Eldoret Main", "county": "Uasin Gishu",
    }
    base.update(keys)
    dates = pd.date_range(start, periods=n_weeks, freq="W-MON")
    rows = []
    for i, date in enumerate(dates):
        rows.append(make_observation(
            **base,
            date=str(date.date()),
            wholesale_price=price + i,
            wholesale_per_kg=price + i,
            retail_price=None,
            retail_per_kg=None,
        ))
    return pd.DataFrame(rows)
