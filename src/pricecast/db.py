"""SQLite storage (schema v2).

Changes from v1, all of them correctness fixes:
  * `county`, `grade` and `sex` join the observations primary key. Without
    county, two markets that share a name in different counties silently merged
    into one price series; without grade/sex, livestock rows collide.
  * prices are stored both as quoted and normalised to KES/kg.
  * `forecasts` is keyed by `as_of` as well, so re-running keeps every vintage.
    "What did we tell farmers three weeks ago, and were we right?" is the
    question a ministry or funder will ask first, and v1 could not answer it.
  * new tables for the delivery layer: subscriptions, farm-gate reports
    (the crowdsourced ground truth), and query telemetry.

The reads/writes used by the request path (API, USSD) are all plain selects
against `forecasts`/`observations` — no model runs inside a request.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import DB_PATH

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
  commodity TEXT NOT NULL,
  classification TEXT NOT NULL,
  grade TEXT NOT NULL DEFAULT '-',
  sex TEXT NOT NULL DEFAULT '-',
  market TEXT NOT NULL,
  county TEXT NOT NULL,
  date TEXT NOT NULL,
  wholesale_price REAL,
  retail_price REAL,
  price_unit TEXT,
  wholesale_per_kg REAL,
  retail_per_kg REAL,
  kg_per_unit REAL,
  unit_basis TEXT,
  supply_volume REAL,
  n_reports INTEGER NOT NULL DEFAULT 1,
  quality_flag INTEGER NOT NULL DEFAULT 0,
  quality_reason TEXT,
  source_file TEXT NOT NULL,
  PRIMARY KEY (commodity, classification, grade, sex, market, county, date)
);
CREATE INDEX IF NOT EXISTS idx_obs_commodity_date ON observations (commodity, date);
CREATE INDEX IF NOT EXISTS idx_obs_county ON observations (county, commodity);

CREATE TABLE IF NOT EXISTS ingest_log (
  source_file TEXT, commodity TEXT, n_rows_raw INTEGER, n_rows_after_agg INTEGER,
  date_min TEXT, date_max TEXT, n_distinct_dates INTEGER, n_markets INTEGER,
  pct_missing_wholesale REAL, pct_missing_retail REAL, pct_missing_volume REAL,
  n_unparseable_prices INTEGER, n_bad_dates INTEGER, n_junk_rows INTEGER,
  n_unconvertible_units INTEGER, hit_row_cap INTEGER,
  loaded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS forecasts (
  commodity TEXT, classification TEXT, grade TEXT DEFAULT '-', sex TEXT DEFAULT '-',
  market TEXT, county TEXT,
  as_of TEXT, target_week_start TEXT, horizon_weeks INTEGER,
  price_type TEXT,
  p10 REAL, p50 REAL, p90 REAL, unit TEXT,
  last_price REAL, last_price_date TEXT,
  tier TEXT, method TEXT, confidence TEXT,
  anomaly_flag INTEGER DEFAULT 0, anomaly_note TEXT,
  sms_text TEXT,
  generated_at TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (commodity, classification, grade, sex, market, county,
               as_of, target_week_start, price_type)
);
CREATE INDEX IF NOT EXISTS idx_fc_lookup ON forecasts (commodity, county, market, horizon_weeks);

CREATE TABLE IF NOT EXISTS subscriptions (
  phone TEXT NOT NULL,
  commodity TEXT NOT NULL,
  county TEXT NOT NULL,
  market TEXT,
  language TEXT NOT NULL DEFAULT 'en',
  created_at TEXT DEFAULT (datetime('now')),
  active INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (phone, commodity, county, market)
);

CREATE TABLE IF NOT EXISTS farm_gate_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT,
  commodity TEXT NOT NULL,
  county TEXT NOT NULL,
  market TEXT,
  offer_kes_per_kg REAL,
  sold INTEGER,
  reference_wholesale REAL,
  reference_floor_low REAL,
  reference_floor_high REAL,
  reported_at TEXT DEFAULT (datetime('now')),
  channel TEXT DEFAULT 'ussd'
);

CREATE TABLE IF NOT EXISTS query_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT, channel TEXT, commodity TEXT, county TEXT, market TEXT,
  queried_at TEXT DEFAULT (datetime('now'))
);
"""

OBS_COLS = [
    "commodity", "classification", "grade", "sex", "market", "county", "date",
    "wholesale_price", "retail_price", "price_unit",
    "wholesale_per_kg", "retail_per_kg", "kg_per_unit", "unit_basis",
    "supply_volume", "n_reports", "quality_flag", "quality_reason", "source_file",
]

KEY_COLS = ["commodity", "classification", "grade", "sex", "market", "county", "date"]

FORECAST_COLS = [
    "commodity", "classification", "grade", "sex", "market", "county",
    "as_of", "target_week_start", "horizon_weeks", "price_type",
    "p10", "p50", "p90", "unit", "last_price", "last_price_date",
    "tier", "method", "confidence", "anomaly_flag", "anomaly_note", "sms_text",
]


class SchemaMismatch(RuntimeError):
    pass


@dataclass
class UpsertStats:
    inserted: int = 0
    merged: int = 0
    unchanged: int = 0


def connect(
    db_path: Path | str = DB_PATH, check_same_thread: bool = True
) -> sqlite3.Connection:
    """Open (and create/upgrade-check) the store.

    `check_same_thread=False` is only for a connection deliberately shared
    across threads (the API test client). The API itself opens one connection
    per request, which is the safe pattern under uvicorn's thread pool.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not db_path.exists()
    conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if not fresh:
        _assert_compatible(conn, db_path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    return conn


def _assert_compatible(conn: sqlite3.Connection, db_path: Path) -> None:
    """Refuse to write v2 rows into a v1 file rather than corrupting keys."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "observations" not in tables:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(observations)")}
    if "wholesale_per_kg" in cols:
        return
    raise SchemaMismatch(
        f"{db_path} uses the v1 schema (no county/grade in the primary key).\n"
        "The raw KAMIS exports are the source of truth, so the fix is to rebuild:\n"
        f"    rm {db_path}\n"
        "    python run_demo.py"
    )


# --- observations -----------------------------------------------------------

def upsert_observations(conn: sqlite3.Connection, df: pd.DataFrame) -> UpsertStats:
    """Merge on the full observation key; new non-null values fill gaps.

    Re-ingesting an overlapping export is a no-op, which is what makes the
    'pull KAMIS in overlapping chunks' workflow safe.
    """
    stats = UpsertStats()
    if df.empty:
        return stats
    placeholders = ",".join("?" * len(OBS_COLS))
    insert_sql = f"""
        INSERT INTO observations ({",".join(OBS_COLS)})
        VALUES ({placeholders})
        ON CONFLICT(commodity, classification, grade, sex, market, county, date) DO UPDATE SET
          wholesale_price  = COALESCE(excluded.wholesale_price, wholesale_price),
          retail_price     = COALESCE(excluded.retail_price, retail_price),
          wholesale_per_kg = COALESCE(excluded.wholesale_per_kg, wholesale_per_kg),
          retail_per_kg    = COALESCE(excluded.retail_per_kg, retail_per_kg),
          supply_volume    = COALESCE(excluded.supply_volume, supply_volume),
          price_unit       = COALESCE(price_unit, excluded.price_unit),
          kg_per_unit      = COALESCE(kg_per_unit, excluded.kg_per_unit),
          unit_basis       = COALESCE(unit_basis, excluded.unit_basis),
          n_reports        = MAX(n_reports, excluded.n_reports),
          quality_flag     = MAX(quality_flag, excluded.quality_flag),
          quality_reason   = COALESCE(quality_reason, excluded.quality_reason)
    """
    select_key = ",".join(KEY_COLS)
    existing = {
        tuple(r[:7]): r[7:]
        for r in conn.execute(
            f"SELECT {select_key}, wholesale_price, retail_price, supply_volume FROM observations"
        )
    }
    frame = df.reindex(columns=OBS_COLS)
    # callers that never ran the plausibility screen still get valid rows
    frame["quality_flag"] = (
        pd.to_numeric(frame["quality_flag"], errors="coerce").fillna(0).astype(int)
    )
    frame["n_reports"] = pd.to_numeric(frame["n_reports"], errors="coerce").fillna(1).astype(int)
    rows = frame.astype(object).where(pd.notna(frame), None)
    for row in rows.itertuples(index=False):
        key = tuple(getattr(row, c) for c in KEY_COLS)
        prev = existing.get(key)
        if prev is None:
            stats.inserted += 1
        else:
            gains = (
                (prev[0] is None and row.wholesale_price is not None)
                or (prev[1] is None and row.retail_price is not None)
                or (prev[2] is None and row.supply_volume is not None)
            )
            stats.merged += 1 if gains else 0
            stats.unchanged += 0 if gains else 1
        old = prev or (None, None, None)
        existing[key] = (
            row.wholesale_price if row.wholesale_price is not None else old[0],
            row.retail_price if row.retail_price is not None else old[1],
            row.supply_volume if row.supply_volume is not None else old[2],
        )
        conn.execute(insert_sql, tuple(row))
    conn.commit()
    return stats


def read_observations(
    conn: sqlite3.Connection,
    commodity: str | None = None,
    include_flagged: bool = False,
) -> pd.DataFrame:
    """Screened observations by default; flagged rows are opt-in for auditing."""
    clauses, params = [], []
    if not include_flagged:
        clauses.append("quality_flag = 0")
    if commodity:
        clauses.append("commodity = ?")
        params.append(commodity)
    query = "SELECT * FROM observations"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    return pd.read_sql_query(query, conn, params=tuple(params))


def log_ingest(conn: sqlite3.Connection, reports: list) -> None:
    for report in reports:
        record = report.to_dict()
        record["hit_row_cap"] = int(record["hit_row_cap"])
        cols = ",".join(record)
        conn.execute(
            f"INSERT INTO ingest_log ({cols}) VALUES ({','.join('?' * len(record))})",
            list(record.values()),
        )
    conn.commit()


def coverage_report(conn: sqlite3.Connection) -> pd.DataFrame:
    df = read_observations(conn)
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"])
    rows = []
    for (com, cls), g in df.groupby(["commodity", "classification"]):
        weeks = g["date"].dt.to_period("W").nunique()
        span_weeks = max(1, (g["date"].max() - g["date"].min()).days // 7 + 1)
        dates = sorted(g["date"].unique())
        largest_gap = max(
            ((pd.Timestamp(b) - pd.Timestamp(a)).days
             for a, b in zip(dates, dates[1:], strict=False)),
            default=0,
        )
        rows.append({
            "commodity": com, "classification": cls,
            "date_min": g["date"].min().date(), "date_max": g["date"].max().date(),
            "distinct_weeks": weeks, "span_weeks": span_weeks,
            "week_coverage_pct": round(100 * weeks / span_weeks),
            "n_markets": g["market"].nunique(), "n_counties": g["county"].nunique(),
            "largest_gap_days": largest_gap, "n_rows": len(g),
        })
    return pd.DataFrame(rows).sort_values(["commodity", "classification"]).reset_index(drop=True)


# --- forecasts --------------------------------------------------------------

def write_forecasts(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    if df.empty:
        return
    sub = df.reindex(columns=FORECAST_COLS)
    rows = sub.astype(object).where(pd.notna(sub), None)
    conn.executemany(
        f"INSERT OR REPLACE INTO forecasts ({','.join(FORECAST_COLS)}) "
        f"VALUES ({','.join('?' * len(FORECAST_COLS))})",
        list(rows.itertuples(index=False, name=None)),
    )
    conn.commit()


def set_sms_text(conn: sqlite3.Connection, row: dict, text: str) -> None:
    conn.execute(
        "UPDATE forecasts SET sms_text=? WHERE commodity=? AND classification=? AND market=? "
        "AND county=? AND as_of=? AND horizon_weeks=?",
        (text, row["commodity"], row["classification"], row["market"], row["county"],
         row["as_of"], row["horizon_weeks"]),
    )
    conn.commit()


def latest_as_of(conn: sqlite3.Connection, commodity: str | None = None) -> str | None:
    query = "SELECT MAX(as_of) FROM forecasts"
    params: tuple = ()
    if commodity:
        query += " WHERE commodity = ?"
        params = (commodity,)
    row = conn.execute(query, params).fetchone()
    return row[0] if row else None


def read_forecasts(
    conn: sqlite3.Connection,
    commodity: str,
    county: str | None = None,
    market: str | None = None,
    horizon: int | None = None,
) -> pd.DataFrame:
    """Latest vintage only — older vintages stay on disk for accuracy audits."""
    query = [
        "SELECT * FROM forecasts WHERE commodity = ?",
        "AND as_of = (SELECT MAX(as_of) FROM forecasts WHERE commodity = ?)",
    ]
    params: list = [commodity, commodity]
    if county:
        query.append("AND county = ?")
        params.append(county)
    if market:
        query.append("AND market = ?")
        params.append(market)
    if horizon:
        query.append("AND horizon_weeks = ?")
        params.append(horizon)
    return pd.read_sql_query(" ".join(query), conn, params=params)


# --- delivery layer ---------------------------------------------------------

def add_subscription(conn: sqlite3.Connection, phone: str, commodity: str,
                     county: str, market: str | None, language: str = "en") -> None:
    conn.execute(
        "INSERT INTO subscriptions (phone, commodity, county, market, language, active) "
        "VALUES (?,?,?,?,?,1) "
        "ON CONFLICT(phone, commodity, county, market) DO UPDATE SET "
        "active=1, language=excluded.language",
        (phone, commodity, county, market or "", language),
    )
    conn.commit()


def list_subscriptions(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM subscriptions WHERE active = 1", conn)


def add_farm_gate_report(conn: sqlite3.Connection, **kwargs) -> int:
    cols = [
        "phone", "commodity", "county", "market", "offer_kes_per_kg", "sold",
        "reference_wholesale", "reference_floor_low", "reference_floor_high", "channel",
    ]
    values = [kwargs.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO farm_gate_reports ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        values,
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def farm_gate_gap(conn: sqlite3.Connection) -> pd.DataFrame:
    """Reported broker offer vs the wholesale reference — the impact metric."""
    return pd.read_sql_query(
        "SELECT commodity, county, COUNT(*) n, "
        "ROUND(AVG(offer_kes_per_kg), 2) avg_offer, "
        "ROUND(AVG(reference_wholesale), 2) avg_wholesale, "
        "ROUND(AVG(reference_floor_low), 2) avg_floor_low, "
        "ROUND(AVG(100.0 * (reference_wholesale - offer_kes_per_kg) "
        "/ NULLIF(reference_wholesale, 0)), 1) avg_gap_pct "
        "FROM farm_gate_reports WHERE offer_kes_per_kg IS NOT NULL "
        "GROUP BY commodity, county",
        conn,
    )


def log_query(conn: sqlite3.Connection, phone: str | None, channel: str,
              commodity: str | None, county: str | None, market: str | None) -> None:
    conn.execute(
        "INSERT INTO query_log (phone, channel, commodity, county, market) VALUES (?,?,?,?,?)",
        (phone, channel, commodity, county, market),
    )
    conn.commit()
