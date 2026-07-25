"""The product core: what is my crop worth, near me, today.

This is the layer the USSD/SMS/API surfaces actually use. It answers the
question a farmer has while a broker is standing in the yard — *what did this
crop fetch at the markets near me in the last few days, and what is a
defensible floor once transport and levies come out* — using only observed
prices plus the netback registries. No model is involved, which is exactly why
it is the default surface: it is the part of the system that cannot be wrong
about the future because it does not claim anything about the future.

Forecasts are an optional enrichment layered on top (see forecast.py), shown
only where the backtest says the model beats "last known price".
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field

import pandas as pd

from . import geo, netback
from .names import canonical_commodity, canonical_county, canonical_market

DEFAULT_MAX_AGE_DAYS = 21
TREND_WEEKS = 4


@dataclass
class MarketPrice:
    market: str
    county: str
    price_type: str
    price_kes_per_kg: float
    price_date: str
    days_old: int
    distance_km: float | None = None
    distance_precision: str = "unknown"
    trend_pct: float | None = None
    trend_label: str = "unknown"
    n_recent_obs: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PriceCard:
    """Everything one USSD screen / SMS / API response needs."""

    commodity: str
    origin_county: str
    as_of: str
    markets: list[MarketPrice] = field(default_factory=list)
    best: MarketPrice | None = None
    floor: dict | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "commodity": self.commodity,
            "origin_county": self.origin_county,
            "as_of": self.as_of,
            "markets": [m.to_dict() for m in self.markets],
            "best_market": self.best.to_dict() if self.best else None,
            "floor": self.floor,
            "warnings": self.warnings,
        }


def _price_expr(price_type: str) -> str:
    return "wholesale_per_kg" if price_type == "wholesale" else "retail_per_kg"


def latest_prices(
    conn: sqlite3.Connection,
    commodity: str,
    county: str | None = None,
    market: str | None = None,
    price_type: str = "wholesale",
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    reference_date: str | None = None,
) -> pd.DataFrame:
    """Most recent usable observation per (county, market) for one commodity.

    `reference_date` exists so the same code can be demoed against a historical
    extract without pretending old prices are current; it defaults to today.
    """
    column = _price_expr(price_type)
    params: list = [canonical_commodity(commodity)]
    # quality_flag = 0 keeps enumerator typos (0.02 KES/kg onions) off a farmer's screen
    where = [f"commodity = ? AND quality_flag = 0 AND {column} IS NOT NULL AND {column} > 0"]
    if county:
        where.append("county = ?")
        params.append(canonical_county(county))
    if market:
        where.append("market = ?")
        params.append(canonical_market(market))
    query = (
        f"SELECT county, market, date, {column} AS price_kes_per_kg "
        f"FROM observations WHERE {' AND '.join(where)}"
    )
    df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return df

    reference = pd.Timestamp(reference_date) if reference_date else pd.Timestamp.today().normalize()
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] <= reference]
    if df.empty:
        return df
    df["days_old"] = (reference - df["date"]).dt.days

    recent = df[df["days_old"] <= max_age_days]
    counts = (
        recent.groupby(["county", "market"]).size().rename("n_recent_obs").reset_index()
    )
    latest = (
        recent.sort_values("date")
        .groupby(["county", "market"], as_index=False)
        .last()
        .merge(counts, on=["county", "market"], how="left")
    )
    latest["price_type"] = price_type
    return latest


def price_trend(
    conn: sqlite3.Connection,
    commodity: str,
    county: str,
    market: str,
    price_type: str = "wholesale",
    weeks: int = TREND_WEEKS,
    reference_date: str | None = None,
) -> tuple[float | None, str]:
    """Percent change between the latest price and the mean `weeks` ago."""
    column = _price_expr(price_type)
    df = pd.read_sql_query(
        f"SELECT date, {column} AS price FROM observations "
        f"WHERE commodity = ? AND county = ? AND market = ? AND quality_flag = 0 "
        f"AND {column} IS NOT NULL AND {column} > 0 ORDER BY date",
        conn,
        params=[canonical_commodity(commodity), canonical_county(county),
                canonical_market(market)],
    )
    if len(df) < 2:
        return None, "unknown"
    reference = pd.Timestamp(reference_date) if reference_date else pd.Timestamp.today().normalize()
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] <= reference]
    if len(df) < 2:
        return None, "unknown"

    latest_price = float(df.iloc[-1]["price"])
    cutoff = df.iloc[-1]["date"] - pd.Timedelta(weeks=weeks)
    baseline_rows = df[(df["date"] <= cutoff)]
    if baseline_rows.empty:
        baseline_rows = df.iloc[:-1]
    baseline = float(baseline_rows["price"].tail(4).mean())
    if not baseline:
        return None, "unknown"
    change = 100 * (latest_price - baseline) / baseline
    if change > 3:
        label = "rising"
    elif change < -3:
        label = "falling"
    else:
        label = "steady"
    return round(change, 1), label


def price_card(
    conn: sqlite3.Connection,
    commodity: str,
    origin_county: str,
    limit: int = 3,
    price_type: str = "wholesale",
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    consignment_kg: float | None = None,
    reference_date: str | None = None,
) -> PriceCard:
    """Nearest markets with recent prices, ranked, with a netback floor for the best one."""
    commodity = canonical_commodity(commodity)
    origin_county = canonical_county(origin_county)
    reference = pd.Timestamp(reference_date) if reference_date else pd.Timestamp.today().normalize()
    card = PriceCard(commodity=commodity, origin_county=origin_county,
                     as_of=str(reference.date()))

    latest = latest_prices(
        conn, commodity, price_type=price_type, max_age_days=max_age_days,
        reference_date=reference_date,
    )
    if latest.empty:
        card.warnings.append(
            f"No {commodity} prices reported in the last {max_age_days} days."
        )
        return card

    candidates = list(zip(latest["county"], latest["market"], strict=True))
    ranked = geo.nearest_markets(origin_county, candidates, limit=max(limit * 3, 10))
    if not ranked:
        card.warnings.append(
            f"No coordinates on file for {origin_county}; showing markets unranked."
        )
        ranked = []

    distance_by_market = {(d.county.lower(), d.market.lower()): d for d in ranked}
    rows = []
    for record in latest.to_dict("records"):
        key = (canonical_county(record["county"]).lower(),
               canonical_market(record["market"]).lower())
        dist = distance_by_market.get(key)
        change, label = price_trend(
            conn, commodity, record["county"], record["market"],
            price_type=price_type, reference_date=reference_date,
        )
        rows.append(MarketPrice(
            market=record["market"], county=record["county"], price_type=price_type,
            price_kes_per_kg=round(float(record["price_kes_per_kg"]), 2),
            price_date=str(pd.Timestamp(record["date"]).date()),
            days_old=int(record["days_old"]),
            distance_km=dist.road_km if dist else None,
            distance_precision=dist.precision if dist else "unknown",
            trend_pct=change, trend_label=label,
            n_recent_obs=int(record.get("n_recent_obs") or 0),
        ))

    rows.sort(key=lambda m: (m.distance_km is None, m.distance_km or 0, m.days_old))
    card.markets = rows[:limit]
    if not card.markets:
        return card

    # "Best" = highest price among the nearby markets, not merely the nearest.
    card.best = max(card.markets, key=lambda m: m.price_kes_per_kg)
    estimate = netback.estimate(
        commodity=commodity,
        wholesale_kes_per_kg=card.best.price_kes_per_kg,
        origin_county=origin_county,
        market=card.best.market,
        market_county=card.best.county,
        consignment_kg=consignment_kg,
    )
    card.floor = estimate.to_dict()
    card.warnings.extend(estimate.warnings)
    stale = [m for m in card.markets if m.days_old > 7]
    if stale:
        card.warnings.append(
            f"{len(stale)} of {len(card.markets)} markets last reported more than a week ago."
        )
    return card


def available_commodities(
    conn: sqlite3.Connection,
    max_age_days: int | None = None,
    reference_date: str | None = None,
) -> list[str]:
    """All commodities, or only those with a usable price within `max_age_days`."""
    if max_age_days is None:
        return [r[0] for r in conn.execute(
            "SELECT DISTINCT commodity FROM observations ORDER BY commodity"
        )]
    reference = pd.Timestamp(reference_date) if reference_date else pd.Timestamp.today().normalize()
    cutoff = (reference - pd.Timedelta(days=max_age_days)).date()
    rows = conn.execute(
        "SELECT DISTINCT commodity FROM observations "
        "WHERE date >= ? AND date <= ? AND quality_flag = 0 ORDER BY commodity",
        (str(cutoff), str(reference.date())),
    )
    return [r[0] for r in rows]


def available_counties(conn: sqlite3.Connection, commodity: str | None = None) -> list[str]:
    query = "SELECT DISTINCT county FROM observations"
    params: tuple = ()
    if commodity:
        query += " WHERE commodity = ?"
        params = (canonical_commodity(commodity),)
    return sorted(r[0] for r in conn.execute(query + " ORDER BY county", params) if r[0])


def available_markets(
    conn: sqlite3.Connection, commodity: str, county: str | None = None
) -> list[dict]:
    query = "SELECT DISTINCT county, market FROM observations WHERE commodity = ?"
    params: list = [canonical_commodity(commodity)]
    if county:
        query += " AND county = ?"
        params.append(canonical_county(county))
    return [
        {"county": c, "market": m}
        for c, m in conn.execute(query + " ORDER BY county, market", params)
    ]
