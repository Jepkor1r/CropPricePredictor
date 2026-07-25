"""Rolling-origin backtest: is the model better than 'last known price'?

For each horizon, test origins run on a monthly grid over the last ~20% of each
series' observed weeks (per-commodity — the crops' eras don't overlap). At each
origin the pooled model is retrained on data whose *target* falls at or before
the origin, then scored on that month's test targets. Retrains are capped at
MAX_ORIGINS per horizon.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import model as M
from .features import SERIES_KEYS, MIN_OBS_MODEL, make_features

MAX_ORIGINS = 8
TEST_FRACTION = 0.2
MIN_TEST_WEEKS = 6


def _flag_test_rows(feats: pd.DataFrame) -> pd.Series:
    """Mark the last 20% (min 6) of observed weeks per eligible series."""
    flag = pd.Series(False, index=feats.index)
    for _, g in feats.groupby(SERIES_KEYS, observed=True):
        obs = g[g["price"].notna()]
        if len(obs) < MIN_OBS_MODEL:
            continue
        n_test = max(MIN_TEST_WEEKS, int(len(obs) * TEST_FRACTION))
        cutoff = obs["week"].iloc[-n_test]
        flag.loc[g.index[g["week"] >= cutoff]] = True
    return flag


def run_backtest(panel: pd.DataFrame, horizons=M.HORIZONS) -> pd.DataFrame:
    records = []
    for h in horizons:
        feats = make_features(panel, h)
        feats["is_test"] = _flag_test_rows(feats)
        testable = feats[
            feats["is_test"] & feats["target_price"].notna()
            & feats["anchor_log"].notna() & feats["last_obs_price"].notna()
        ]
        if testable.empty:
            continue

        months = sorted(testable["target_week"].dt.to_period("M").unique())
        if len(months) > MAX_ORIGINS:
            idx = np.linspace(0, len(months) - 1, MAX_ORIGINS).round().astype(int)
            months = [months[i] for i in sorted(set(idx))]

        for month in months:
            month_start = month.to_timestamp()
            test = testable[testable["target_week"].dt.to_period("M") == month]
            if test.empty:
                continue
            train = feats[feats["target_week"] < month_start]
            if train["y"].notna().sum() < 100:
                continue
            booster = M.train_global(train, alpha=0.5)
            pred = np.exp(booster.predict(test[M.FEATURE_COLS])) * np.exp(
                test["anchor_log"].to_numpy()
            )
            actual = test["target_price"].to_numpy()
            naive = test["last_obs_price"].to_numpy()
            seasonal = _seasonal_preds(panel, test)

            df = test[["commodity", "target_week"]].copy()
            df["horizon"] = h
            df["ape_model"] = np.abs(pred - actual) / actual
            df["ape_naive"] = np.abs(naive - actual) / actual
            df["ape_seasonal"] = np.where(
                np.isnan(seasonal), np.nan, np.abs(seasonal - actual) / actual
            )
            records.append(df)

    if not records:
        return pd.DataFrame()
    all_pts = pd.concat(records, ignore_index=True)
    metrics = (
        all_pts.groupby(["commodity", "horizon"], observed=True)
        .agg(
            n=("ape_model", "size"),
            mape_model=("ape_model", "mean"),
            mape_naive=("ape_naive", "mean"),
            mape_seasonal=("ape_seasonal", "mean"),
        )
        .reset_index()
    )
    for c in ("mape_model", "mape_naive", "mape_seasonal"):
        metrics[c] = (100 * metrics[c]).round(1)
    metrics["skill_vs_naive"] = (metrics["mape_model"] / metrics["mape_naive"]).round(2)
    return metrics


def _seasonal_preds(panel: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    preds = []
    for row in test.itertuples():
        keys = tuple(getattr(row, k) for k in SERIES_KEYS)
        p = M.seasonal_naive(panel, keys, row.target_week.month, upto_week=row.week)
        preds.append(np.nan if p is None else p)
    return np.array(preds)


def commodity_mape_lookup(metrics: pd.DataFrame, horizon: int = 1) -> dict[str, float]:
    if metrics.empty:
        return {}
    h = metrics[metrics["horizon"] == horizon]
    return dict(zip(h["commodity"], h["mape_model"]))


def commodity_skill_lookup(metrics: pd.DataFrame, horizon: int = 1) -> dict[str, float]:
    if metrics.empty:
        return {}
    h = metrics[metrics["horizon"] == horizon]
    return dict(zip(h["commodity"], h["skill_vs_naive"]))
