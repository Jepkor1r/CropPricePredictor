"""Baselines, the pooled LightGBM quantile model, and fallback tiering.

Fallback policy (changed from v1): when the model fails to beat "last known
price" for a commodity, the fallback is **naive-with-band**, not the seasonal
mean. v1 demoted losers to a seasonal baseline that its own backtest showed was
worse still (tomatoes h=1: seasonal 43.9 MAPE vs naive 23.5). Falling back to a
*worse* predictor because the better one underperformed is not conservatism, it
is a bug.
"""
from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from .config import (
    HORIZONS,
    MAX_STALE_WEEKS,
    MIN_OBS_MODEL,
    MIN_OBS_SEASONAL,
    QUANTILES,
)
from .features import CATEGORICALS, FEATURE_COLS, SERIES_KEYS

__all__ = [
    "HORIZONS", "QUANTILES", "tier_for_series", "train_global", "train_quantile_set",
    "predict_prices", "naive_forecast", "naive_band", "seasonal_naive",
    "confidence_for", "Prediction",
]

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

DEFAULT_BAND = 0.15         # +/-15% when a series has no change history at all
MIN_DIFFS_FOR_BAND = 8


@dataclass(frozen=True)
class Prediction:
    p10: float
    p50: float
    p90: float
    method: str


def tier_for_series(n_weekly_obs: int, weeks_since_last_obs: float) -> str:
    if n_weekly_obs < MIN_OBS_SEASONAL or weeks_since_last_obs > MAX_STALE_WEEKS:
        return "insufficient_data"
    if n_weekly_obs < MIN_OBS_MODEL:
        return "seasonal_fallback"
    return "model"


def train_global(features: pd.DataFrame, alpha: float) -> lgb.LGBMRegressor:
    """One pooled quantile model over every series with a valid target row."""
    train = features[features["y"].notna() & features["anchor_log"].notna()]
    model = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **LGB_PARAMS)
    model.fit(train[FEATURE_COLS], train["y"], categorical_feature=CATEGORICALS)
    return model


def train_quantile_set(features: pd.DataFrame) -> dict[float, lgb.LGBMRegressor]:
    return {q: train_global(features, q) for q in QUANTILES}


def predict_prices(models: dict[float, lgb.LGBMRegressor], rows: pd.DataFrame) -> pd.DataFrame:
    """Predict the log-ratio and re-anchor to KES. Returns p10/p50/p90."""
    preds = {q: m.predict(rows[FEATURE_COLS]) for q, m in models.items()}
    anchor = np.exp(rows["anchor_log"].to_numpy())
    stacked = np.sort(
        np.vstack([anchor * np.exp(preds[q]) for q in sorted(preds)]), axis=0
    )
    return pd.DataFrame(
        {"p10": stacked[0], "p50": stacked[1], "p90": stacked[2]}, index=rows.index
    )


def naive_forecast(rows: pd.DataFrame) -> pd.Series:
    """Last observed weekly price at time t."""
    return rows["last_obs_price"]


def _series_slice(panel: pd.DataFrame, keys: tuple, upto_week=None) -> pd.DataFrame:
    mask = pd.Series(True, index=panel.index)
    for col, val in zip(SERIES_KEYS, keys, strict=True):
        mask &= panel[col] == val
    out = panel[mask]
    if upto_week is not None:
        out = out[out["week"] <= upto_week]
    return out.sort_values("week")


def _log_change_quantiles(prices: pd.Series, horizon: int) -> tuple[float, float] | None:
    """Empirical 10th/90th percentile of h-week log price changes."""
    logp = np.log(prices.astype(float))
    diffs = (logp.shift(-horizon) - logp).dropna()
    if len(diffs) < MIN_DIFFS_FOR_BAND:
        return None
    return float(diffs.quantile(0.1)), float(diffs.quantile(0.9))


def naive_band(
    panel: pd.DataFrame, keys: tuple, horizon: int, upto_week=None
) -> Prediction | None:
    """Last observed price, with an interval from that series' own volatility.

    Falls back to the commodity-wide change distribution when the series is too
    short, and to a flat +/-15% when even that is unavailable. The point
    forecast is always the last observed price, which is the benchmark the
    model has to beat before it is allowed to speak.
    """
    series = _series_slice(panel, keys, upto_week)
    observed = series["price"].dropna()
    if observed.empty:
        return None
    last = float(observed.iloc[-1])

    quantiles = _log_change_quantiles(series.set_index("week")["price"], horizon)
    method = "naive_band(series)"
    if quantiles is None:
        commodity = keys[0]
        pooled = panel[(panel["commodity"] == commodity) & panel["price"].notna()]
        if upto_week is not None:
            pooled = pooled[pooled["week"] <= upto_week]
        diffs = []
        for _, group in pooled.groupby(SERIES_KEYS, dropna=False):
            logp = np.log(group.sort_values("week")["price"].astype(float))
            diffs.append((logp.shift(-horizon) - logp).dropna())
        pooled_diffs = pd.concat(diffs) if diffs else pd.Series(dtype=float)
        if len(pooled_diffs) >= MIN_DIFFS_FOR_BAND:
            quantiles = (float(pooled_diffs.quantile(0.1)), float(pooled_diffs.quantile(0.9)))
            method = "naive_band(commodity)"
        else:
            quantiles = (np.log(1 - DEFAULT_BAND), np.log(1 + DEFAULT_BAND))
            method = "naive_band(default)"

    low, high = quantiles
    p10 = last * float(np.exp(low))
    p90 = last * float(np.exp(high))
    # A strongly trending series can produce an empirical interval that sits
    # entirely above (or below) the last price. The point forecast stays the
    # last observed price - that is the benchmark the model must beat - so the
    # interval is widened to contain it rather than published out of order.
    return Prediction(
        p10=round(min(p10, last), 2),
        p50=round(last, 2),
        p90=round(max(p90, last), 2),
        method=method,
    )


def seasonal_naive(
    panel: pd.DataFrame, keys: tuple, target_month: int, upto_week=None
) -> float | None:
    """Same-month mean of the series' own history. Kept as a backtest reference."""
    series = _series_slice(panel, keys, upto_week)
    observed = series[series["price"].notna()]
    if observed.empty:
        return None
    same_month = observed[observed["week"].dt.month == target_month]["price"]
    if len(same_month) >= 2:
        return float(same_month.mean())
    return float(observed["price"].mean())


def confidence_for(
    commodity_mape: float | None, p10: float, p50: float, p90: float, tier: str = "model"
) -> str:
    """Backtested accuracy first, interval width as a veto."""
    if tier != "model" or commodity_mape is None:
        level = "low"
    elif commodity_mape < 10:
        level = "high"
    elif commodity_mape < 20:
        level = "medium"
    else:
        level = "low"
    if p50 and (p90 - p10) / p50 > 0.5:
        level = "low"
    return level
