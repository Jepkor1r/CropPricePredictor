"""Weekly panel and leakage-safe features per price series.

A series is (commodity, classification, grade, sex, market, county). County is
part of the key because market names repeat across counties; grade/sex are part
of it because livestock prices differ by both and would otherwise be averaged
into nonsense.

Modelling is weekly: per-market daily coverage is too sparse and irregular for a
daily model. The training target is scale-invariant — log(price[t+h]) minus the
log of the 4-week rolling mean at t — so 2005-era tomato prices and 2026-era
maize prices pool into one model without nominal-KES level effects.

Cross-market features are computed *within* price_type. In v1 they were not,
which meant a wholesale series was being compared against a national median
polluted by retail quotes that run 30-50% higher.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MIN_OBS_MODEL, MIN_OBS_SEASONAL  # noqa: F401  (re-exported)

SERIES_KEYS = ["commodity", "classification", "grade", "sex", "market", "county"]

CATEGORICALS = ["commodity", "classification", "market", "county", "price_type"]
FEATURE_COLS = CATEGORICALS + [
    "lag1", "lag2", "lag4", "lag8",
    "roll4_mean_log", "roll4_std_log", "roll12_mean_log", "roll12_std_log",
    "momentum4",
    "month", "month_sin", "month_cos", "woy_sin", "woy_cos",
    "weeks_since_obs",
    "county_median_log", "national_median_log", "rel_to_national",
    "log_volume", "roll4_volume",
]


def resolve_price_basis(obs: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """Put every row of a series on one price basis, converting where possible.

    Preference order per series: KES/kg (from the unit conversion at ingest),
    otherwise the series' modal quoted unit. Rows on another unquotable unit are
    dropped and counted — v1 dropped them silently.
    """
    obs = obs.copy()
    for col in ("wholesale_per_kg", "retail_per_kg", "wholesale_price", "retail_price"):
        if col not in obs:
            obs[col] = np.nan
    if "price_unit" not in obs:
        obs["price_unit"] = None

    obs["_has_kg"] = obs["wholesale_per_kg"].notna() | obs["retail_per_kg"].notna()

    kept = []
    dropped = 0
    for keys, group in obs.groupby(SERIES_KEYS, dropna=False):
        # The basis is decided per *series*, not per row: mixing a KES/kg row
        # with a KES/gunia row inside one series produces a price history that
        # jumps by two orders of magnitude and silently wrecks every feature.
        if group["_has_kg"].any():
            keep = group[group["_has_kg"]].copy()
            keep["wholesale_value"] = keep["wholesale_per_kg"]
            keep["retail_value"] = keep["retail_per_kg"]
            keep["basis_unit"] = "Kg"
        else:
            quoted_units = group["price_unit"].dropna()
            if quoted_units.empty:
                dropped += len(group)
                continue
            modal = quoted_units.mode().iloc[0]
            keep = group[group["price_unit"] == modal].copy()
            keep["wholesale_value"] = keep["wholesale_price"]
            keep["retail_value"] = keep["retail_price"]
            keep["basis_unit"] = modal
        if verbose and len(group) != len(keep):
            print(
                f"  [unit] {keys[0]} @ {keys[4]}, {keys[5]}: kept "
                f"{keep['basis_unit'].iloc[0]}, dropped {len(group) - len(keep)} row(s)"
            )
        dropped += len(group) - len(keep)
        kept.append(keep)

    frames = [f for f in kept if not f.empty]
    if not frames:
        return obs.assign(wholesale_value=np.nan, retail_value=np.nan, basis_unit=None).iloc[0:0]
    out = pd.concat(frames, ignore_index=True).drop(columns=["_has_kg"])
    if verbose and dropped:
        print(f"  [unit] {dropped} rows dropped: no kg equivalence and not the series' modal unit")
    return out


def choose_price_type(obs: pd.DataFrame) -> pd.DataFrame:
    """Wholesale is primary (it is what a broker benchmarks against); retail is a fallback."""
    counts = obs.groupby(SERIES_KEYS, dropna=False).agg(
        n_w=("wholesale_value", "count"), n_r=("retail_value", "count")
    )
    counts["price_type"] = np.where(
        (counts["n_w"] >= MIN_OBS_SEASONAL) | (counts["n_w"] >= counts["n_r"]),
        "wholesale", "retail",
    )
    return obs.merge(counts[["price_type"]].reset_index(), on=SERIES_KEYS, how="left")


def build_weekly_panel(obs: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    """One row per series-week inside each series' own observed range.

    Unobserved weeks inside the range are present with NaN price; the panel
    never extends past a series' first/last observation.
    """
    obs = resolve_price_basis(obs, verbose=verbose)
    if obs.empty:
        return obs
    obs = choose_price_type(obs)
    obs["price"] = np.where(
        obs["price_type"] == "wholesale", obs["wholesale_value"], obs["retail_value"]
    )
    obs = obs[obs["price"].notna() & (obs["price"] > 0)].copy()
    if obs.empty:
        return obs
    obs["date"] = pd.to_datetime(obs["date"])
    obs["week"] = obs["date"].dt.to_period("W-SUN").dt.start_time

    weekly = obs.groupby(SERIES_KEYS + ["week"], as_index=False, dropna=False).agg(
        price_type=("price_type", "first"),
        price_unit=("basis_unit", "first"),
        price=("price", "mean"),
        volume=("supply_volume", "sum"),
        n_obs_week=("date", "count"),
        last_obs_date=("date", "max"),
    )

    frames = []
    for keys, group in weekly.groupby(SERIES_KEYS, dropna=False):
        group = group.set_index("week").sort_index()
        full = pd.date_range(group.index.min(), group.index.max(), freq="W-MON")
        group = group.reindex(full)
        for col, val in zip(SERIES_KEYS, keys, strict=True):
            group[col] = val
        group["price_type"] = group["price_type"].ffill().bfill()
        group["price_unit"] = group["price_unit"].ffill().bfill()
        group.index.name = "week"
        frames.append(group.reset_index())
    panel = pd.concat(frames, ignore_index=True)
    # reindexing gap weeks yields object columns; force numeric before any maths
    for col in ("price", "volume", "n_obs_week"):
        panel[col] = pd.to_numeric(panel[col], errors="coerce")
    panel["log_price"] = np.log(panel["price"])
    return panel


def make_features(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Feature/target table for one horizon. Every feature uses data <= week t."""
    df = panel.sort_values(SERIES_KEYS + ["week"]).copy()
    grouped = df.groupby(SERIES_KEYS, group_keys=False, dropna=False)

    for lag in (1, 2, 4, 8):
        df[f"lag{lag}"] = grouped["log_price"].shift(lag)
    df["roll4_mean_log"] = grouped["log_price"].transform(
        lambda s: s.rolling(4, min_periods=2).mean())
    df["roll4_std_log"] = grouped["log_price"].transform(
        lambda s: s.rolling(4, min_periods=2).std())
    df["roll12_mean_log"] = grouped["log_price"].transform(
        lambda s: s.rolling(12, min_periods=2).mean())
    df["roll12_std_log"] = grouped["log_price"].transform(
        lambda s: s.rolling(12, min_periods=2).std())
    df["momentum4"] = df["log_price"] - df["lag4"]

    df["month"] = df["week"].dt.month
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    woy = df["week"].dt.isocalendar().week.astype(float)
    df["woy_sin"] = np.sin(2 * np.pi * woy / 52)
    df["woy_cos"] = np.cos(2 * np.pi * woy / 52)

    df["weeks_since_obs"] = grouped["price"].transform(
        lambda s: s.notna().cumsum().groupby(s.notna().cumsum()).cumcount()
    ).astype(float)

    # Cross-market signals, computed within price_type so wholesale series are
    # never benchmarked against retail quotes.
    df["national_median_log"] = df.groupby(
        ["commodity", "price_type", "week"], observed=True
    )["log_price"].transform("median")
    df["rel_to_national"] = df["log_price"] - df["national_median_log"]
    df["county_median_log"] = (
        df.groupby(["commodity", "price_type", "county", "week"],
                   group_keys=False, observed=True)["log_price"]
        .apply(_leave_one_out_median)
    )

    df["log_volume"] = np.log1p(df["volume"])
    df["roll4_volume"] = grouped["log_volume"].transform(
        lambda s: s.rolling(4, min_periods=1).mean())

    df["last_obs_price"] = grouped["price"].ffill()
    df["anchor_log"] = grouped["roll4_mean_log"].ffill()

    df["target_log_price"] = grouped["log_price"].shift(-horizon)
    df["target_price"] = grouped["price"].shift(-horizon)
    df["target_week"] = grouped["week"].shift(-horizon)
    df["y"] = df["target_log_price"] - df["anchor_log"]

    for col in CATEGORICALS:
        df[col] = df[col].astype("category")
    return df


def _leave_one_out_median(s: pd.Series) -> pd.Series:
    """County median for the same commodity-week, excluding the row's own market."""
    values = s.dropna()
    if len(values) <= 1:
        return pd.Series(np.nan, index=s.index)
    total = len(values)
    out = {}
    for idx in s.index:
        others = values.drop(idx, errors="ignore")
        out[idx] = others.median() if len(others) and len(others) < total + 1 else np.nan
    return pd.Series(out)


def series_stats(panel: pd.DataFrame) -> pd.DataFrame:
    """Per-series observation counts and last-observed week, used for tiering."""
    return panel[panel["price"].notna()].groupby(SERIES_KEYS, dropna=False).agg(
        price_type=("price_type", "first"),
        price_unit=("price_unit", "first"),
        n_weekly_obs=("price", "count"),
        first_week=("week", "min"),
        last_week=("week", "max"),
        last_price=("price", "last"),
        last_obs_date=("last_obs_date", "max"),
    ).reset_index()
