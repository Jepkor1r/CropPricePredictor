"""Generate forecasts for every series and persist them to the forecasts table.

`as_of` is per-commodity (the last date observed for that crop) — the sample
exports cover wildly different eras, so there is no shared "today".
Anomaly detection is deterministic; Claude only phrases it later.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import model as M
from .features import SERIES_KEYS, make_features, series_stats


def _anomaly(latest: pd.DataFrame, row) -> tuple[int, str | None]:
    """Latest weekly price vs same-week county and national medians."""
    week_peers = latest[
        (latest["commodity"] == row.commodity) & (latest["week"] == row.last_week)
    ]
    checks = [
        ("county", week_peers[week_peers["county"] == row.county]),
        ("national", week_peers),
    ]
    for scope, peers in checks:
        peers = peers[peers["market"] != row.market]["price"].dropna()
        if len(peers) < 3:
            continue
        med = peers.median()
        mad = (peers - med).abs().median()
        dev = (row.last_price - med) / med
        z = 0.6745 * (row.last_price - med) / mad if mad > 0 else 0.0
        if abs(dev) > 0.30 or abs(z) > 2:
            direction = "above" if dev > 0 else "below"
            return 1, f"{abs(dev) * 100:.0f}% {direction} {scope} median ({len(peers) + 1} markets)"
    return 0, None


def generate_forecasts(panel: pd.DataFrame, mape_by_commodity: dict[str, float]) -> pd.DataFrame:
    stats = series_stats(panel)
    as_of = panel[panel["price"].notna()].groupby("commodity")["week"].max().rename("as_of_week")
    as_of_date = (
        panel[panel["price"].notna()].groupby("commodity")["last_obs_date"].max().rename("as_of")
    )
    stats = stats.merge(as_of, on="commodity").merge(as_of_date, on="commodity")
    stats["weeks_stale"] = ((stats["as_of_week"] - stats["last_week"]).dt.days // 7).astype(int)
    stats["tier"] = [
        M.tier_for_series(n, s) for n, s in zip(stats["n_weekly_obs"], stats["weeks_stale"])
    ]

    # Pooled quantile models per horizon, trained on all data
    feats_by_h = {h: make_features(panel, h) for h in M.HORIZONS}
    models_by_h = {h: M.train_quantile_set(feats_by_h[h]) for h in M.HORIZONS}

    latest_obs = panel[panel["price"].notna()]
    out_rows = []
    for row in stats.itertuples():
        keys = tuple(getattr(row, k) for k in SERIES_KEYS)
        anomaly_flag, anomaly_note = (0, None)
        if row.tier != "insufficient_data":
            anomaly_flag, anomaly_note = _anomaly(latest_obs, row)

        for h in M.HORIZONS:
            target_week = row.as_of_week + pd.Timedelta(weeks=h)
            base = dict(
                commodity=row.commodity, classification=row.classification,
                market=row.market, county=row.county,
                as_of=str(pd.Timestamp(row.as_of).date()),
                target_week_start=str(target_week.date()),
                horizon_weeks=h, price_type=row.price_type,
                unit=f"KES/{row.price_unit or 'Kg'}",
                last_price=round(float(row.last_price), 2),
                last_price_date=str(pd.Timestamp(row.last_obs_date).date()),
                tier=row.tier, anomaly_flag=anomaly_flag, anomaly_note=anomaly_note,
                p10=None, p50=None, p90=None, confidence="none", sms_text=None,
            )
            if row.tier == "insufficient_data":
                out_rows.append(base)
                continue

            if row.tier == "model":
                feats = feats_by_h[h]
                mask = pd.Series(True, index=feats.index)
                for col, val in zip(SERIES_KEYS, keys):
                    mask &= feats[col] == val
                srows = feats[mask & feats["anchor_log"].notna()]
                if len(srows):
                    last_row = srows.iloc[[-1]]
                    pred = M.predict_prices(models_by_h[h], last_row).iloc[0]
                    base.update(
                        p10=round(pred.p10, 2), p50=round(pred.p50, 2), p90=round(pred.p90, 2),
                        confidence=M.confidence_for(
                            mape_by_commodity.get(row.commodity), pred.p10, pred.p50, pred.p90
                        ),
                    )
                    out_rows.append(base)
                    continue
                base["tier"] = "seasonal_fallback"  # no usable feature row

            p50 = M.seasonal_naive(panel, keys, target_week.month)
            if p50 is None:
                base["tier"] = "insufficient_data"
            else:
                spread = 0.20 * p50
                base.update(
                    p10=round(p50 - spread, 2), p50=round(p50, 2), p90=round(p50 + spread, 2),
                    confidence="low",
                )
            out_rows.append(base)

    return pd.DataFrame(out_rows)


def nearest_covered_market(forecasts: pd.DataFrame, row: pd.Series) -> str | None:
    """For insufficient-data messages: a covered market, same county preferred."""
    ok = forecasts[
        (forecasts["commodity"] == row["commodity"])
        & (forecasts["tier"] != "insufficient_data")
        & (forecasts["horizon_weeks"] == 1)
    ]
    same_county = ok[ok["county"] == row["county"]]
    pick = same_county if len(same_county) else ok
    return pick["market"].iloc[0] if len(pick) else None
