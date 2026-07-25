"""Plausibility screening for reported prices.

KAMIS is enumerator-entered and contains gross data-entry errors. Real examples
from the exports in this repo, all for Dry Onions whose median is ~50 KES/kg:

    Gakoromone, Meru      2021-12-03    0.02 KES/kg
    Nkubu, Meru           2021-09-14    0.13 KES/kg
    Sibanga, Trans Nzoia  2021-12-31  2100.00 KES/kg

Left alone these do three kinds of damage: they are shown to farmers as real
prices, they blow up error metrics (dividing by 0.02 gave a 7019% MAPE in the
backtest), and they drag rolling means and cross-market medians around.

Policy: flag, never delete. Flagged rows stay in `observations` with a reason so
the screening is auditable and reversible; the panel builder and the price
service both filter them out. The rule is a ratio band against a robust
per-commodity, per-year median, which is deliberately crude and explainable —
"we ignore quotes more than 8x away from the typical price for that crop that
year" is a sentence you can defend to a county officer.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RATIO_FACTOR = 8.0        # flag beyond 8x or 1/8x the robust median
MIN_ROWS_FOR_YEAR = 20    # below this, fall back to the commodity-wide median
ABSOLUTE_FLOOR = 0.5      # KES/kg: nothing edible trades below this


def _reference_medians(df: pd.DataFrame, value_col: str) -> pd.Series:
    """Median price per (commodity, year), falling back to commodity-wide."""
    year = pd.to_datetime(df["date"], errors="coerce").dt.year
    frame = pd.DataFrame({
        "commodity": df["commodity"], "year": year, "value": df[value_col]
    }).dropna(subset=["value"])
    by_year = frame.groupby(["commodity", "year"])["value"].agg(["median", "size"])
    by_commodity = frame.groupby("commodity")["value"].median()

    keys = list(zip(df["commodity"], year, strict=True))
    medians = []
    for commodity, yr in keys:
        row = by_year["median"].get((commodity, yr))
        count = by_year["size"].get((commodity, yr), 0)
        if row is None or pd.isna(row) or count < MIN_ROWS_FOR_YEAR:
            row = by_commodity.get(commodity, np.nan)
        medians.append(row)
    return pd.Series(medians, index=df.index, dtype=float)


def flag_implausible(
    obs: pd.DataFrame, factor: float = RATIO_FACTOR
) -> tuple[pd.Series, pd.Series]:
    """Return (flag 0/1, reason) aligned to `obs`.

    A row is flagged when either quoted price is impossibly small or sits
    outside [median/factor, median*factor] for its commodity and year.
    """
    if obs.empty:
        return pd.Series(dtype=int), pd.Series(dtype=object)

    value_col = "wholesale_per_kg" if "wholesale_per_kg" in obs else "wholesale_price"
    fallback_col = "retail_per_kg" if "retail_per_kg" in obs else "retail_price"
    values = obs[value_col]
    if fallback_col in obs:
        values = values.fillna(obs[fallback_col])

    reference = _reference_medians(obs.assign(_v=values), "_v")
    flags = pd.Series(0, index=obs.index, dtype=int)
    reasons = pd.Series(None, index=obs.index, dtype=object)

    too_small = values.notna() & (values < ABSOLUTE_FLOOR)
    flags[too_small] = 1
    reasons[too_small] = f"price below {ABSOLUTE_FLOOR} KES/kg - data entry error"

    usable = values.notna() & reference.notna() & (reference > 0) & (~too_small)
    ratio = values / reference
    high = usable & (ratio > factor)
    low = usable & (ratio < 1 / factor)
    flags[high | low] = 1
    reasons[high] = (
        ratio[high].round(1).astype(str) + "x the typical price for this crop/year"
    )
    reasons[low] = (
        "1/" + (1 / ratio[low]).round(1).astype(str) + " of the typical price for this crop/year"
    )
    return flags, reasons


def screening_summary(obs: pd.DataFrame) -> pd.DataFrame:
    """Per-commodity count of what the screen removed — printed at ingest."""
    if "quality_flag" not in obs or obs.empty:
        return pd.DataFrame()
    flagged = obs[obs["quality_flag"] == 1]
    if flagged.empty:
        return pd.DataFrame()
    value_col = "wholesale_per_kg" if "wholesale_per_kg" in obs else "wholesale_price"
    return (
        flagged.groupby("commodity")
        .agg(
            flagged_rows=("quality_flag", "size"),
            min_price=(value_col, "min"),
            max_price=(value_col, "max"),
            example=("quality_reason", "first"),
        )
        .reset_index()
    )
