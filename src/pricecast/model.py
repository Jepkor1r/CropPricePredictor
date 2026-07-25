"""Baselines, the pooled LightGBM quantile model, and fallback tiering."""
from __future__ import annotations

import numpy as np
import pandas as pd
import lightgbm as lgb

from .features import FEATURE_COLS, CATEGORICALS, MIN_OBS_MODEL, MIN_OBS_SEASONAL, MAX_STALE_WEEKS

HORIZONS = (1, 2, 4)
QUANTILES = (0.1, 0.5, 0.9)

LGB_PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    num_leaves=31,
    min_child_samples=20,
    subsample=0.9,
    subsample_freq=1,
    colsample_bytree=0.9,
    verbose=-1,
)


def tier_for_series(n_weekly_obs: int, weeks_since_last_obs: int) -> str:
    if n_weekly_obs < MIN_OBS_SEASONAL or weeks_since_last_obs > MAX_STALE_WEEKS:
        return "insufficient_data"
    if n_weekly_obs < MIN_OBS_MODEL:
        return "seasonal_fallback"
    return "model"


def train_global(features: pd.DataFrame, alpha: float) -> lgb.LGBMRegressor:
    """One pooled quantile model over every series with a valid target row."""
    train = features[features["y"].notna() & features["anchor_log"].notna()]
    model = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **LGB_PARAMS)
    model.fit(
        train[FEATURE_COLS], train["y"],
        categorical_feature=CATEGORICALS,
    )
    return model


def train_quantile_set(features: pd.DataFrame) -> dict[float, lgb.LGBMRegressor]:
    return {q: train_global(features, q) for q in QUANTILES}


def predict_prices(models: dict[float, lgb.LGBMRegressor], rows: pd.DataFrame) -> pd.DataFrame:
    """Predict and re-anchor the log-ratio back to KES. Returns p10/p50/p90."""
    out = rows[["anchor_log"]].copy()
    for q, m in models.items():
        out[f"q{q}"] = m.predict(rows[FEATURE_COLS])
    anchor = np.exp(rows["anchor_log"].to_numpy())
    p10 = anchor * np.exp(out["q0.1"].to_numpy())
    p50 = anchor * np.exp(out["q0.5"].to_numpy())
    p90 = anchor * np.exp(out["q0.9"].to_numpy())
    # quantile crossings can happen with independently trained models — sort
    stacked = np.sort(np.vstack([p10, p50, p90]), axis=0)
    return pd.DataFrame(
        {"p10": stacked[0], "p50": stacked[1], "p90": stacked[2]}, index=rows.index
    )


def naive_forecast(rows: pd.DataFrame) -> pd.Series:
    """Last observed weekly price at time t."""
    return rows["last_obs_price"]


def seasonal_naive(panel: pd.DataFrame, keys: tuple, target_month: int,
                   upto_week=None) -> float | None:
    """Same-month mean of the series' own history; None if <2 observations."""
    from .features import SERIES_KEYS
    g = panel
    for col, val in zip(SERIES_KEYS, keys):
        g = g[g[col] == val]
    g = g[g["price"].notna()]
    if upto_week is not None:
        g = g[g["week"] <= upto_week]
    m = g[g["week"].dt.month == target_month]["price"]
    if len(m) >= 2:
        return float(m.mean())
    return float(g["price"].mean()) if len(g) else None


def confidence_for(commodity_mape: float | None, p10: float, p50: float, p90: float) -> str:
    if commodity_mape is None:
        conf = "low"
    elif commodity_mape < 10:
        conf = "high"
    elif commodity_mape < 20:
        conf = "medium"
    else:
        conf = "low"
    if p50 and (p90 - p10) / p50 > 0.5:  # interval wider than ±25% of p50
        conf = "low"
    return conf
