"""Generate forecasts for every series and persist them with their vintage.

Two policy changes from v1:

1. **Staleness is judged against wall-clock today by default.** v1 measured
   staleness against each commodity's own last observation, so a series whose
   data stopped in 2011 still looked "fresh" and was forecast as if current.
   Use `as_of_mode='per_commodity'` only to demo on historical extracts, and
   the caller is expected to shout about it.

2. **A suppressed model does not leave its numbers behind.** When a commodity
   fails to beat naive in the backtest, the series is re-forecast with
   `naive_band` and labelled accordingly. v1 relabelled the tier but kept the
   LightGBM numbers, producing rows whose label and content disagreed.
"""
from __future__ import annotations

import pandas as pd

from . import geo
from . import model as M
from .config import HORIZONS
from .features import SERIES_KEYS, make_features, series_stats

TIER_MODEL = "model"
TIER_FALLBACK = "naive_fallback"
TIER_NONE = "insufficient_data"


def _anomaly(latest: pd.DataFrame, row) -> tuple[int, str | None]:
    """Latest weekly price vs same-week county and national peers (same price type)."""
    peers_week = latest[
        (latest["commodity"] == row.commodity)
        & (latest["price_type"] == row.price_type)
        & (latest["week"] == row.last_week)
    ]
    checks = [
        ("county", peers_week[peers_week["county"] == row.county]),
        ("national", peers_week),
    ]
    for scope, peers in checks:
        values = peers[peers["market"] != row.market]["price"].dropna()
        if len(values) < 3:
            continue
        median = values.median()
        if not median:
            continue
        mad = (values - median).abs().median()
        deviation = (row.last_price - median) / median
        z = 0.6745 * (row.last_price - median) / mad if mad > 0 else 0.0
        if abs(deviation) > 0.30 or abs(z) > 2:
            direction = "above" if deviation > 0 else "below"
            return 1, (
                f"{abs(deviation) * 100:.0f}% {direction} {scope} median "
                f"({len(values) + 1} markets)"
            )
    return 0, None


def resolve_as_of(panel: pd.DataFrame, mode: str = "today") -> dict[str, pd.Timestamp]:
    """Reference 'now' per commodity: wall clock, or the extract's own last week."""
    observed = panel[panel["price"].notna()]
    commodities = observed["commodity"].unique()
    if mode == "per_commodity":
        return observed.groupby("commodity")["week"].max().to_dict()
    today_week = pd.Timestamp.today().normalize().to_period("W-SUN").start_time
    return dict.fromkeys(commodities, today_week)


def generate_forecasts(
    panel: pd.DataFrame,
    mape_by_commodity: dict[str, float] | None = None,
    as_of_mode: str = "today",
    suppress_model_for: set[str] | None = None,
    horizons=HORIZONS,
) -> pd.DataFrame:
    """One row per (series, horizon). Never raises on thin data — it tiers down."""
    if panel.empty:
        return pd.DataFrame()
    mape_by_commodity = mape_by_commodity or {}
    suppress_model_for = suppress_model_for or set()

    stats = series_stats(panel)
    as_of_week = resolve_as_of(panel, as_of_mode)
    stats["as_of_week"] = stats["commodity"].map(as_of_week)
    stats["weeks_stale"] = (
        (stats["as_of_week"] - stats["last_week"]).dt.days // 7
    ).astype(int)
    stats["tier"] = [
        M.tier_for_series(n, s)
        for n, s in zip(stats["n_weekly_obs"], stats["weeks_stale"], strict=True)
    ]
    stats.loc[stats["tier"] == "seasonal_fallback", "tier"] = TIER_FALLBACK

    needs_model = (stats["tier"] == TIER_MODEL) & (~stats["commodity"].isin(suppress_model_for))
    feats_by_h: dict[int, pd.DataFrame] = {}
    models_by_h: dict[int, dict] = {}
    if needs_model.any():
        for horizon in horizons:
            feats_by_h[horizon] = make_features(panel, horizon)
            models_by_h[horizon] = M.train_quantile_set(feats_by_h[horizon])

    observed = panel[panel["price"].notna()]
    rows = []
    for row in stats.itertuples():
        keys = tuple(getattr(row, key) for key in SERIES_KEYS)
        anomaly_flag, anomaly_note = (0, None)
        if row.tier != TIER_NONE:
            anomaly_flag, anomaly_note = _anomaly(observed, row)
        suppressed = row.commodity in suppress_model_for

        for horizon in horizons:
            target_week = row.as_of_week + pd.Timedelta(weeks=horizon)
            record = {
                "commodity": row.commodity, "classification": row.classification,
                "grade": row.grade, "sex": row.sex,
                "market": row.market, "county": row.county,
                "as_of": str(pd.Timestamp(row.as_of_week).date()),
                "target_week_start": str(target_week.date()),
                "horizon_weeks": horizon,
                "price_type": row.price_type,
                "unit": f"KES/{row.price_unit or 'Kg'}",
                "last_price": round(float(row.last_price), 2),
                "last_price_date": str(pd.Timestamp(row.last_obs_date).date()),
                "weeks_stale": int(row.weeks_stale),
                "n_weekly_obs": int(row.n_weekly_obs),
                "tier": row.tier, "method": "none", "confidence": "none",
                "anomaly_flag": anomaly_flag, "anomaly_note": anomaly_note,
                "p10": None, "p50": None, "p90": None, "sms_text": None,
            }

            if row.tier == TIER_NONE:
                record["method"] = "none (stale or too few observations)"
                rows.append(record)
                continue

            prediction = None
            if row.tier == TIER_MODEL and not suppressed:
                prediction = _model_prediction(feats_by_h[horizon], models_by_h[horizon], keys)
            suffix = ""
            if prediction is None:
                prediction = M.naive_band(panel, keys, horizon)
                record["tier"] = TIER_FALLBACK
                if suppressed:
                    suffix = " [model suppressed: lost to naive in backtest]"
            if prediction is None:
                record["tier"] = TIER_NONE
                record["method"] = "none (no usable history)"
                rows.append(record)
                continue

            record.update(
                p10=prediction.p10, p50=prediction.p50, p90=prediction.p90,
                method=prediction.method + suffix,
                confidence=M.confidence_for(
                    mape_by_commodity.get(row.commodity),
                    prediction.p10, prediction.p50, prediction.p90,
                    tier=record["tier"],
                ),
            )
            rows.append(record)

    return pd.DataFrame(rows)


def _model_prediction(feats: pd.DataFrame, models: dict, keys: tuple) -> M.Prediction | None:
    mask = pd.Series(True, index=feats.index)
    for col, val in zip(SERIES_KEYS, keys, strict=True):
        mask &= feats[col] == val
    usable = feats[mask & feats["anchor_log"].notna()]
    if usable.empty:
        return None
    last_row = usable.iloc[[-1]]
    pred = M.predict_prices(models, last_row).iloc[0]
    return M.Prediction(
        p10=round(float(pred.p10), 2),
        p50=round(float(pred.p50), 2),
        p90=round(float(pred.p90), 2),
        method="lgbm_quantile",
    )


def nearest_covered_market(forecasts: pd.DataFrame, row) -> str | None:
    """Geographically nearest market that actually has a usable forecast.

    v1 returned 'the first row in the dataframe, same county preferred', which
    is not nearest by any definition. This ranks real candidates by road
    distance from the farmer's county.
    """
    get = row.get if hasattr(row, "get") else (lambda k: getattr(row, k))
    covered = forecasts[
        (forecasts["commodity"] == get("commodity"))
        & (forecasts["tier"] != TIER_NONE)
        & (forecasts["horizon_weeks"] == 1)
    ]
    if covered.empty:
        return None
    candidates = list(zip(covered["county"], covered["market"], strict=True))
    ranked = geo.nearest_markets(get("county"), candidates, limit=1)
    if ranked:
        return ranked[0].market
    same_county = covered[covered["county"] == get("county")]
    pick = same_county if len(same_county) else covered
    return pick["market"].iloc[0]
