"""Read-mostly HTTP API over the SQLite store.

Contract with the rest of the system: **nothing here trains or forecasts.** The
model runs in a batch job; requests only read `observations`, `forecasts`, and
the static registries. That is what keeps a USSD screen inside the telco
timeout, and what lets the API scale to a dashboard and a WhatsApp bot later
without touching the science.

Run: uvicorn pricecast.api:app --reload
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Any

try:
    from fastapi import Depends, FastAPI, Form, HTTPException, Query
    from fastapi.responses import PlainTextResponse
    from pydantic import BaseModel
except ModuleNotFoundError as exc:  # pragma: no cover - import-time guard
    raise ModuleNotFoundError(
        "The API layer needs FastAPI. Install with:  pip install '.[api]'"
    ) from exc

from . import db, explain, geo, netback, prices, sms, ussd
from .config import DB_PATH, PILOT_CROPS
from .names import canonical_commodity, canonical_county, canonical_market

app = FastAPI(
    title="PriceCast API",
    version="0.2.0",
    description="Localized crop price transparency and farm-gate floor estimation.",
)


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = db.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


class ReportIn(BaseModel):
    phone: str | None = None
    commodity: str
    county: str
    market: str | None = None
    offer_kes_per_kg: float
    sold: bool | None = None
    channel: str = "api"


class SubscriptionIn(BaseModel):
    phone: str
    commodity: str
    county: str
    market: str | None = None
    language: str = "en"


@app.get("/health")
def health(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    row = conn.execute(
        "SELECT COUNT(*), MAX(date) FROM observations"
    ).fetchone()
    return {
        "status": "ok",
        "observations": row[0],
        "latest_observation": row[1],
        "schema_version": db.SCHEMA_VERSION,
    }


@app.get("/pilot")
def pilot() -> dict[str, Any]:
    """The scoped pilot: which crop/county pairs this deployment claims to serve."""
    return {"crops": PILOT_CROPS}


@app.get("/commodities")
def commodities(
    fresh_days: int | None = Query(None, description="Only commodities seen this recently"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return {"commodities": prices.available_commodities(conn, fresh_days)}


@app.get("/counties")
def counties(
    commodity: str | None = None, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    return {"counties": prices.available_counties(conn, commodity)}


@app.get("/markets")
def markets(
    commodity: str,
    county: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    rows = prices.available_markets(conn, commodity, county)
    return {"markets": rows, "geo_coverage": geo.coverage_stats(
        [(r["county"], r["market"]) for r in rows]
    )}


@app.get("/prices/latest")
def latest(
    commodity: str,
    county: str | None = None,
    market: str | None = None,
    price_type: str = "wholesale",
    max_age_days: int = prices.DEFAULT_MAX_AGE_DAYS,
    reference_date: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    df = prices.latest_prices(
        conn, commodity, county, market, price_type, max_age_days, reference_date
    )
    if df.empty:
        return {"commodity": canonical_commodity(commodity), "prices": []}
    df = df.assign(date=df["date"].astype(str))
    return {"commodity": canonical_commodity(commodity), "prices": df.to_dict("records")}


@app.get("/card")
def card(
    commodity: str,
    county: str,
    limit: int = 3,
    consignment_kg: float | None = None,
    reference_date: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    """The core product response: nearby prices + an itemised farm-gate floor."""
    result = prices.price_card(
        conn, commodity, county, limit=limit,
        consignment_kg=consignment_kg, reference_date=reference_date,
    )
    payload = result.to_dict()
    payload["sms_preview"] = explain.card_sms(result)
    return payload


@app.get("/netback")
def netback_endpoint(
    commodity: str,
    wholesale_kes_per_kg: float,
    origin_county: str,
    market: str,
    market_county: str,
    consignment_kg: float | None = None,
) -> dict[str, Any]:
    estimate = netback.estimate(
        commodity=canonical_commodity(commodity),
        wholesale_kes_per_kg=wholesale_kes_per_kg,
        origin_county=canonical_county(origin_county),
        market=canonical_market(market),
        market_county=canonical_county(market_county),
        consignment_kg=consignment_kg,
    )
    return estimate.to_dict()


@app.get("/forecast")
def forecast(
    commodity: str,
    county: str | None = None,
    market: str | None = None,
    horizon: int | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    df = db.read_forecasts(conn, canonical_commodity(commodity), county, market, horizon)
    if df.empty:
        raise HTTPException(404, "No forecast vintage for that selection")
    return {"as_of": df["as_of"].iloc[0], "forecasts": df.to_dict("records")}


@app.get("/history")
def history(
    commodity: str,
    county: str,
    market: str,
    weeks: int = 12,
    price_type: str = "wholesale",
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    column = "wholesale_per_kg" if price_type == "wholesale" else "retail_per_kg"
    rows = conn.execute(
        f"SELECT date, {column} FROM observations WHERE commodity=? AND county=? AND market=? "
        f"AND quality_flag = 0 AND {column} IS NOT NULL ORDER BY date DESC LIMIT ?",
        (canonical_commodity(commodity), canonical_county(county),
         canonical_market(market), weeks * 7),
    ).fetchall()
    return {"points": [{"date": d, "price_kes_per_kg": p} for d, p in reversed(rows)]}


@app.post("/reports")
def create_report(
    payload: ReportIn, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    """Crowdsourced farm-gate offers — the dataset nobody else in Kenya has."""
    card_now = prices.price_card(conn, payload.commodity, payload.county, limit=1)
    floor = card_now.floor or {}
    report_id = db.add_farm_gate_report(
        conn,
        phone=payload.phone, commodity=canonical_commodity(payload.commodity),
        county=canonical_county(payload.county),
        market=payload.market or (card_now.best.market if card_now.best else None),
        offer_kes_per_kg=payload.offer_kes_per_kg,
        sold=int(payload.sold) if payload.sold is not None else None,
        reference_wholesale=card_now.best.price_kes_per_kg if card_now.best else None,
        reference_floor_low=floor.get("floor_low"),
        reference_floor_high=floor.get("floor_high"),
        channel=payload.channel,
    )
    return {"id": report_id, "reference_floor": floor.get("floor_low")}


@app.post("/subscriptions")
def create_subscription(
    payload: SubscriptionIn, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, str]:
    db.add_subscription(
        conn, payload.phone, canonical_commodity(payload.commodity),
        canonical_county(payload.county), payload.market, payload.language,
    )
    return {"status": "subscribed"}


@app.get("/impact")
def impact(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    """Reported broker offer vs wholesale reference: the metric that matters."""
    return {"farm_gate_gap": db.farm_gate_gap(conn).to_dict("records")}


@app.post("/ussd", response_class=PlainTextResponse)
def ussd_webhook(
    sessionId: str = Form(""),          # noqa: N803 - Africa's Talking field names
    serviceCode: str = Form(""),        # noqa: N803
    phoneNumber: str = Form(""),        # noqa: N803
    text: str = Form(""),
    conn: sqlite3.Connection = Depends(get_conn),
) -> str:
    return ussd.UssdApp(conn).handle(phoneNumber, text).render()


@app.get("/outbox")
def outbox(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return {"messages": sms.outbox(conn).to_dict("records")}
