"""Weekly panel and leakage-safe features per (commodity, classification, market).

Modeling is weekly: per-market daily coverage is too sparse and irregular for a
daily model. The training target is scale-invariant — log(price[t+h]) minus the
log of the 4-week rolling mean at t — so 2005-era tomato prices and 2026-era
maize prices pool into one model without nominal-KES level effects.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SERIES_KEYS = ["commodity", "classification", "market"]
MIN_OBS_MODEL = 26        # weekly obs needed for the LightGBM tier
MIN_OBS_SEASONAL = 8      # below this: insufficient_data
MAX_STALE_WEEKS = 8       # last obs older than this vs as_of: insufficient_data

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


def _dominant_unit(obs: pd.DataFrame) -> pd.DataFrame:
    """Keep only each commodity's dominant price unit; report what was dropped."""
    keep = []
    for com, g in obs.groupby("commodity"):
        units = g["price_unit"].dropna()
        if units.empty:
            continue
        dominant = units.mode().iloc[0]
        excluded = (units != dominant).sum()
        if excluded:
            print(f"  [unit filter] {com}: dropped {excluded} rows not in {dominant}")
        keep.append(g[(g["price_unit"] == dominant) | g["price_unit"].isna()])
    return pd.concat(keep, ignore_index=True)


def choose_price_type(obs: pd.DataFrame) -> pd.DataFrame:
    """Pick wholesale or retail per series (wholesale primary; retail fallback)."""
    counts = obs.groupby(SERIES_KEYS).agg(
        n_w=("wholesale_price", "count"), n_r=("retail_price", "count")
    )
    counts["price_type"] = np.where(
        (counts["n_w"] >= MIN_OBS_SEASONAL) | (counts["n_w"] >= counts["n_r"]),
        "wholesale", "retail",
    )
    return obs.merge(counts[["price_type"]].reset_index(), on=SERIES_KEYS, how="left")


def build_weekly_panel(obs: pd.DataFrame) -> pd.DataFrame:
    """One row per series-week within each series' own observed range.

    Unobserved weeks inside the range are present with NaN price; the panel
    never extends past a series' first/last observation.
    """
    obs = _dominant_unit(obs)
    obs = choose_price_type(obs)
    obs["price"] = np.where(
        obs["price_type"] == "wholesale", obs["wholesale_price"], obs["retail_price"]
    )
    obs = obs[obs["price"].notna() & (obs["price"] > 0)].copy()
    obs["date"] = pd.to_datetime(obs["date"])
    obs["week"] = obs["date"].dt.to_period("W-SUN").dt.start_time  # Monday start

    weekly = obs.groupby(SERIES_KEYS + ["week"], as_index=False).agg(
        county=("county", "first"),
        price_type=("price_type", "first"),
        price_unit=("price_unit", "first"),
        price=("price", "mean"),
        volume=("supply_volume", "sum"),
        n_obs_week=("date", "count"),
        last_obs_date=("date", "max"),
    )

    frames = []
    for keys, g in weekly.groupby(SERIES_KEYS):
        g = g.set_index("week").sort_index()
        full = pd.date_range(g.index.min(), g.index.max(), freq="W-MON")
        g = g.reindex(full)
        for col, val in zip(SERIES_KEYS, keys):
            g[col] = val
        g["county"] = g["county"].ffill().bfill()
        g["price_type"] = g["price_type"].ffill().bfill()
        g["price_unit"] = g["price_unit"].ffill().bfill()
        g.index.name = "week"
        frames.append(g.reset_index())
    panel = pd.concat(frames, ignore_index=True)
    panel["log_price"] = np.log(panel["price"])
    return panel


def make_features(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Feature/target table for one horizon. All features use data <= week t."""
    df = panel.sort_values(SERIES_KEYS + ["week"]).copy()
    g = df.groupby(SERIES_KEYS, group_keys=False)

    for lag in (1, 2, 4, 8):
        df[f"lag{lag}"] = g["log_price"].shift(lag)
    df["roll4_mean_log"] = g["log_price"].transform(
        lambda s: s.rolling(4, min_periods=2).mean())
    df["roll4_std_log"] = g["log_price"].transform(
        lambda s: s.rolling(4, min_periods=2).std())
    df["roll12_mean_log"] = g["log_price"].transform(
        lambda s: s.rolling(12, min_periods=2).mean())
    df["roll12_std_log"] = g["log_price"].transform(
        lambda s: s.rolling(12, min_periods=2).std())
    df["momentum4"] = df["log_price"] - df["lag4"]

    df["month"] = df["week"].dt.month
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    woy = df["week"].dt.isocalendar().week.astype(float)
    df["woy_sin"] = np.sin(2 * np.pi * woy / 52)
    df["woy_cos"] = np.cos(2 * np.pi * woy / 52)

    df["weeks_since_obs"] = g["price"].transform(
        lambda s: (s.notna().cumsum().groupby(s.notna().cumsum()).cumcount())
    ).astype(float)

    # Cross-market signals for the same commodity-week
    grp_nat = df.groupby(["commodity", "week"])["log_price"]
    df["national_median_log"] = grp_nat.transform("median")
    df["rel_to_national"] = df["log_price"] - df["national_median_log"]

    def _loo_median(s: pd.Series) -> pd.Series:
        # county median excluding the row's own market
        vals = s.dropna()
        if len(vals) <= 1:
            return pd.Series(np.nan, index=s.index)
        out = {}
        for idx in s.index:
            others = vals.drop(idx, errors="ignore")
            out[idx] = others.median() if len(others) else np.nan
        return pd.Series(out)

    df["county_median_log"] = (
        df.groupby(["commodity", "county", "week"], group_keys=False)["log_price"]
        .apply(_loo_median)
    )

    df["log_volume"] = np.log1p(df["volume"])
    df["roll4_volume"] = g["log_volume"].transform(
        lambda s: s.rolling(4, min_periods=1).mean())

    # ffill last observed price/anchor forward so gap weeks can still predict
    df["last_obs_price"] = g["price"].ffill()
    df["anchor_log"] = g["roll4_mean_log"].ffill()

    df["target_log_price"] = g["log_price"].shift(-horizon)
    df["target_price"] = g["price"].shift(-horizon)
    df["target_week"] = g["week"].shift(-horizon)
    df["y"] = df["target_log_price"] - df["anchor_log"]

    for c in CATEGORICALS:
        df[c] = df[c].astype("category")
    return df


def series_stats(panel: pd.DataFrame) -> pd.DataFrame:
    """Per-series observation counts and last-observed week, for tiering."""
    return panel[panel["price"].notna()].groupby(SERIES_KEYS).agg(
        county=("county", "first"),
        price_type=("price_type", "first"),
        price_unit=("price_unit", "first"),
        n_weekly_obs=("price", "count"),
        first_week=("week", "min"),
        last_week=("week", "max"),
        last_price=("price", "last"),
        last_obs_date=("last_obs_date", "max"),
    ).reset_index()
