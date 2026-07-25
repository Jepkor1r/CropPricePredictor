"""Storage keys, feature leakage, tiering, and the fallback policy."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from helpers import make_observation, weekly_series
from pricecast import db as DB
from pricecast import forecast as FC
from pricecast import model as M
from pricecast.config import MAX_STALE_WEEKS, MIN_OBS_MODEL, MIN_OBS_SEASONAL
from pricecast.features import SERIES_KEYS, build_weekly_panel, make_features

# --- storage keys -----------------------------------------------------------

def test_same_market_name_in_two_counties_stays_separate(conn):
    """The v1 primary key merged these into one series."""
    rows = pd.DataFrame([
        make_observation(market="Soko Mpya", county="Nyandarua", wholesale_per_kg=40.0),
        make_observation(market="Soko Mpya", county="Kisumu", wholesale_per_kg=70.0),
    ])
    DB.upsert_observations(conn, rows)
    stored = DB.read_observations(conn)
    assert len(stored) == 2
    assert set(stored["county"]) == {"Nyandarua", "Kisumu"}


def test_livestock_sex_does_not_collide(conn):
    rows = pd.DataFrame([
        make_observation(commodity="Cattle", sex="Male", wholesale_per_kg=300.0),
        make_observation(commodity="Cattle", sex="Female", wholesale_per_kg=250.0),
    ])
    DB.upsert_observations(conn, rows)
    assert len(DB.read_observations(conn)) == 2


def test_reingesting_the_same_export_is_a_noop(conn):
    rows = pd.DataFrame([make_observation()])
    first = DB.upsert_observations(conn, rows)
    second = DB.upsert_observations(conn, rows)
    assert first.inserted == 1
    assert second.inserted == 0 and second.unchanged == 1
    assert len(DB.read_observations(conn)) == 1


def test_overlapping_export_fills_gaps_without_duplicating(conn):
    DB.upsert_observations(conn, pd.DataFrame([
        make_observation(retail_price=None, retail_per_kg=None)
    ]))
    stats = DB.upsert_observations(conn, pd.DataFrame([
        make_observation(wholesale_price=None, wholesale_per_kg=None)
    ]))
    stored = DB.read_observations(conn)
    assert stats.merged == 1
    assert len(stored) == 1
    assert stored.iloc[0]["wholesale_per_kg"] == 50.0
    assert stored.iloc[0]["retail_per_kg"] == 60.0


def test_v1_database_is_rejected_rather_than_corrupted(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE observations (commodity TEXT, classification TEXT, market TEXT,"
        " county TEXT, date TEXT, wholesale_price REAL,"
        " PRIMARY KEY (commodity, classification, market, date))"
    )
    old.commit()
    old.close()
    with pytest.raises(DB.SchemaMismatch, match="v1 schema"):
        DB.connect(path)


def test_forecast_vintages_are_retained(conn):
    base = dict(
        commodity="Dry Maize", classification="White Maize", grade="-", sex="-",
        market="Eldoret Main", county="Uasin Gishu", target_week_start="2026-08-03",
        horizon_weeks=1, price_type="wholesale", p10=1, p50=2, p90=3, unit="KES/Kg",
        last_price=2, last_price_date="2026-07-20", tier="model", method="lgbm_quantile",
        confidence="high", anomaly_flag=0, anomaly_note=None, sms_text=None,
    )
    DB.write_forecasts(conn, pd.DataFrame([{**base, "as_of": "2026-07-20"}]))
    DB.write_forecasts(conn, pd.DataFrame([{**base, "as_of": "2026-07-27"}]))
    rows = conn.execute("SELECT COUNT(*), COUNT(DISTINCT as_of) FROM forecasts").fetchone()
    assert rows == (2, 2)


# --- features ---------------------------------------------------------------

def test_panel_has_no_target_leakage():
    panel = build_weekly_panel(weekly_series(30))
    feats = make_features(panel, horizon=2).sort_values("week")
    row = feats.iloc[10]
    assert row["target_price"] == pytest.approx(feats.iloc[12]["price"])
    assert row["lag1"] == pytest.approx(feats.iloc[9]["log_price"])
    assert pd.isna(feats.iloc[-1]["target_price"])


def test_features_never_reference_future_rows():
    panel = build_weekly_panel(weekly_series(30))
    feats = make_features(panel, horizon=1)
    for i in range(5, len(feats)):
        window = feats.iloc[: i + 1]
        assert feats.iloc[i]["roll4_mean_log"] == pytest.approx(
            window["log_price"].tail(4).mean(), nan_ok=True
        )


def test_cross_market_median_is_computed_within_price_type():
    """A wholesale series must not be benchmarked against retail quotes."""
    wholesale = weekly_series(12, market="Eldoret Main")
    retail_rows = weekly_series(12, market="Kitale Municipality", county="Trans Nzoia")
    retail_rows["wholesale_price"] = None
    retail_rows["wholesale_per_kg"] = None
    retail_rows["retail_price"] = 200.0
    retail_rows["retail_per_kg"] = 200.0
    panel = build_weekly_panel(pd.concat([wholesale, retail_rows], ignore_index=True))
    feats = make_features(panel, horizon=1)
    wholesale_rows = feats[feats["price_type"] == "wholesale"]
    assert wholesale_rows["national_median_log"].max() < np.log(200.0)


def test_panel_keeps_counties_separate():
    a = weekly_series(12, market="Soko Mpya", county="Nyandarua")
    b = weekly_series(12, market="Soko Mpya", county="Kisumu", price=90.0)
    panel = build_weekly_panel(pd.concat([a, b], ignore_index=True))
    assert panel.groupby(SERIES_KEYS, dropna=False).ngroups == 2


def test_unconvertible_units_do_not_poison_a_series():
    kg_rows = weekly_series(12)
    odd = weekly_series(3, start="2026-06-01")
    odd["price_unit"] = "Gunia"
    odd["wholesale_per_kg"] = None
    odd["wholesale_price"] = 4000.0
    panel = build_weekly_panel(pd.concat([kg_rows, odd], ignore_index=True))
    assert panel["price"].max() < 1000


# --- tiering and fallbacks --------------------------------------------------

@pytest.mark.parametrize(
    ("n_obs", "stale", "expected"),
    [
        (MIN_OBS_MODEL, 0, "model"),
        (MIN_OBS_MODEL, MAX_STALE_WEEKS + 1, "insufficient_data"),
        (MIN_OBS_SEASONAL, 0, "seasonal_fallback"),
        (MIN_OBS_SEASONAL - 1, 0, "insufficient_data"),
    ],
)
def test_tiering_matrix(n_obs, stale, expected):
    assert M.tier_for_series(n_obs, stale) == expected


def test_naive_band_point_forecast_is_the_last_price():
    panel = build_weekly_panel(weekly_series(30))
    keys = tuple(panel.iloc[0][k] for k in SERIES_KEYS)
    prediction = M.naive_band(panel, keys, horizon=1)
    last = panel[panel["price"].notna()]["price"].iloc[-1]
    assert prediction.p50 == pytest.approx(last)
    assert prediction.p10 <= prediction.p50 <= prediction.p90
    assert prediction.method.startswith("naive_band")


def test_naive_band_widens_with_volatility():
    calm = weekly_series(30)
    volatile = weekly_series(30, market="Kitale Municipality", county="Trans Nzoia")
    swings = np.resize([0.7, 1.4], len(volatile))
    volatile["wholesale_per_kg"] = volatile["wholesale_per_kg"] * swings
    panel = build_weekly_panel(pd.concat([calm, volatile], ignore_index=True))

    def spread(market, county):
        rows = panel[(panel["market"] == market) & (panel["county"] == county)]
        keys = tuple(rows.iloc[0][k] for k in SERIES_KEYS)
        prediction = M.naive_band(panel, keys, horizon=1)
        return (prediction.p90 - prediction.p10) / prediction.p50

    assert spread("Kitale Municipality", "Trans Nzoia") > spread("Eldoret Main", "Uasin Gishu")


def test_naive_band_interval_always_contains_the_point():
    for start_price in (10.0, 500.0):
        panel = build_weekly_panel(weekly_series(30, price=start_price))
        keys = tuple(panel.iloc[0][k] for k in SERIES_KEYS)
        prediction = M.naive_band(panel, keys, horizon=2)
        assert prediction.p10 <= prediction.p50 <= prediction.p90


def test_naive_band_falls_back_to_a_default_spread_for_short_series():
    panel = build_weekly_panel(weekly_series(3))
    keys = tuple(panel.iloc[0][k] for k in SERIES_KEYS)
    prediction = M.naive_band(panel, keys, horizon=1)
    assert prediction.method == "naive_band(default)"


def test_stale_series_are_not_forecast():
    """A 2011 extract must not be presented as a current price."""
    panel = build_weekly_panel(weekly_series(40, start="2011-01-03"))
    out = FC.generate_forecasts(panel, as_of_mode="today")
    assert set(out["tier"]) == {FC.TIER_NONE}
    assert out["p50"].isna().all()


def test_per_commodity_as_of_is_opt_in_only():
    panel = build_weekly_panel(weekly_series(40, start="2011-01-03"))
    out = FC.generate_forecasts(panel, as_of_mode="per_commodity")
    assert (out["tier"] != FC.TIER_NONE).any()


def test_suppressed_commodity_gets_fallback_numbers_not_model_numbers():
    """v1 relabelled the tier but kept the model's p50 — label and content disagreed."""
    panel = build_weekly_panel(weekly_series(40, start="2026-01-05"))
    suppressed = FC.generate_forecasts(
        panel, as_of_mode="per_commodity", suppress_model_for={"Dry Maize"}
    )
    horizon1 = suppressed[suppressed["horizon_weeks"] == 1].iloc[0]
    last_price = panel[panel["price"].notna()]["price"].iloc[-1]
    assert horizon1["tier"] == FC.TIER_FALLBACK
    assert horizon1["method"].startswith("naive_band")
    assert horizon1["p50"] == pytest.approx(last_price)


def test_forecast_rows_carry_their_vintage_and_method():
    panel = build_weekly_panel(weekly_series(40, start="2026-01-05"))
    out = FC.generate_forecasts(panel, as_of_mode="per_commodity")
    assert out["as_of"].notna().all()
    assert out["method"].notna().all()
    assert set(out["horizon_weeks"]) == {1, 2, 4}
