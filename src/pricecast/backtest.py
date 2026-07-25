"""Rolling-origin backtest: is the model better than 'last known price'?

For each horizon, test origins run on a monthly grid over the last ~20% of each
series' observed weeks. At each origin the pooled model is retrained on rows
whose *target* falls before the origin, then scored on that month's targets.
Retrains are capped at MAX_ORIGINS per horizon to keep the demo runnable.

The naive baseline here is the point forecast of `naive_band`, so a skill score
below 1.0 is exactly the condition under which the model is allowed to speak in
production. Anything else is marketing.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import model as M
from .config import HORIZONS, MIN_OBS_MODEL
from .features import SERIES_KEYS, make_features

MAX_ORIGINS = 8
TEST_FRACTION = 0.2
MIN_TEST_WEEKS = 6
MIN_TRAIN_ROWS = 100


def _flag_test_rows(feats: pd.DataFrame) -> pd.Series:
    """Mark the last 20% (min 6) of observed weeks per eligible series."""
    flag = pd.Series(False, index=feats.index)
    for _, group in feats.groupby(SERIES_KEYS, observed=True, dropna=False):
        observed = group[group["price"].notna()]
        if len(observed) < MIN_OBS_MODEL:
            continue
        n_test = max(MIN_TEST_WEEKS, int(len(observed) * TEST_FRACTION))
        cutoff = observed["week"].iloc[-n_test]
        flag.loc[group.index[group["week"] >= cutoff]] = True
    return flag


def run_backtest(panel: pd.DataFrame, horizons=HORIZONS) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame()
    records = []
    for horizon in horizons:
        feats = make_features(panel, horizon)
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
            if train["y"].notna().sum() < MIN_TRAIN_ROWS:
                continue
            booster = M.train_global(train, alpha=0.5)
            pred = np.exp(booster.predict(test[M.FEATURE_COLS])) * np.exp(
                test["anchor_log"].to_numpy()
            )
            actual = test["target_price"].to_numpy()
            naive = test["last_obs_price"].to_numpy()
            seasonal = _seasonal_preds(panel, test)

            frame = test[["commodity", "target_week"]].copy()
            frame["horizon"] = horizon
            frame["ape_model"] = np.abs(pred - actual) / actual
            frame["ape_naive"] = np.abs(naive - actual) / actual
            frame["ape_seasonal"] = np.where(
                np.isnan(seasonal), np.nan, np.abs(seasonal - actual) / actual
            )
            records.append(frame)

    if not records:
        return pd.DataFrame()
    points = pd.concat(records, ignore_index=True)
    metrics = (
        points.groupby(["commodity", "horizon"], observed=True)
        .agg(
            n=("ape_model", "size"),
            mape_model=("ape_model", "mean"),
            mape_naive=("ape_naive", "mean"),
            mape_seasonal=("ape_seasonal", "mean"),
        )
        .reset_index()
    )
    for col in ("mape_model", "mape_naive", "mape_seasonal"):
        metrics[col] = (100 * metrics[col]).round(1)
    metrics["skill_vs_naive"] = (metrics["mape_model"] / metrics["mape_naive"]).round(2)
    metrics["model_wins"] = metrics["skill_vs_naive"] < 1.0
    return metrics


def _seasonal_preds(panel: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    preds = []
    for row in test.itertuples():
        keys = tuple(getattr(row, key) for key in SERIES_KEYS)
        value = M.seasonal_naive(panel, keys, row.target_week.month, upto_week=row.week)
        preds.append(np.nan if value is None else value)
    return np.array(preds)


def commodity_mape_lookup(metrics: pd.DataFrame, horizon: int = 1) -> dict[str, float]:
    if metrics.empty:
        return {}
    subset = metrics[metrics["horizon"] == horizon]
    return dict(zip(subset["commodity"], subset["mape_model"], strict=True))


def commodity_skill_lookup(metrics: pd.DataFrame, horizon: int = 1) -> dict[str, float]:
    if metrics.empty:
        return {}
    subset = metrics[metrics["horizon"] == horizon]
    return dict(zip(subset["commodity"], subset["skill_vs_naive"], strict=True))


def losing_commodities(metrics: pd.DataFrame, horizon: int = 1) -> set[str]:
    """Commodities where the model does not beat naive — model output is suppressed."""
    if metrics.empty:
        return set()
    subset = metrics[(metrics["horizon"] == horizon) & (metrics["skill_vs_naive"] >= 1.0)]
    return set(subset["commodity"])
