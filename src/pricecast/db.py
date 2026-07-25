"""SQLite storage: observations, ingest_log, forecasts.

The forecasts table is the Phase-2 integration contract — the future USSD/SMS
and dashboard layers read it and never re-run the model.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DB_PATH = Path("data/kamis.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
  commodity TEXT NOT NULL,
  classification TEXT NOT NULL,
  market TEXT NOT NULL,
  county TEXT NOT NULL,
  date TEXT NOT NULL,
  wholesale_price REAL,
  retail_price REAL,
  price_unit TEXT,
  supply_volume REAL,
  n_reports INTEGER NOT NULL DEFAULT 1,
  source_file TEXT NOT NULL,
  PRIMARY KEY (commodity, classification, market, date)
);
CREATE TABLE IF NOT EXISTS ingest_log (
  source_file TEXT, commodity TEXT, n_rows_raw INTEGER, n_rows_after_agg INTEGER,
  date_min TEXT, date_max TEXT, n_distinct_dates INTEGER, n_markets INTEGER,
  pct_missing_wholesale REAL, pct_missing_retail REAL, pct_missing_volume REAL,
  n_unparseable_prices INTEGER, n_bad_dates INTEGER, hit_row_cap INTEGER,
  loaded_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS forecasts (
  commodity TEXT, classification TEXT, market TEXT, county TEXT,
  as_of TEXT, target_week_start TEXT, horizon_weeks INTEGER,
  price_type TEXT,
  p10 REAL, p50 REAL, p90 REAL, unit TEXT,
  last_price REAL, last_price_date TEXT,
  tier TEXT, confidence TEXT,
  anomaly_flag INTEGER DEFAULT 0, anomaly_note TEXT,
  sms_text TEXT,
  PRIMARY KEY (commodity, classification, market, target_week_start, price_type)
);
"""

OBS_COLS = [
    "commodity", "classification", "market", "county", "date",
    "wholesale_price", "retail_price", "price_unit", "supply_volume",
    "n_reports", "source_file",
]


@dataclass
class UpsertStats:
    inserted: int = 0
    merged: int = 0      # existing row gained at least one new non-null value
    unchanged: int = 0


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def upsert_observations(conn: sqlite3.Connection, df: pd.DataFrame) -> UpsertStats:
    """Merge rows on the (commodity, classification, market, date) key.

    New non-null prices fill gaps in existing rows (COALESCE semantics); rows
    that add nothing count as unchanged, so re-ingesting the same export is a
    no-op.
    """
    stats = UpsertStats()
    existing = {
        (r[0], r[1], r[2], r[3]): (r[4], r[5], r[6])
        for r in conn.execute(
            "SELECT commodity, classification, market, date,"
            " wholesale_price, retail_price, supply_volume FROM observations"
        )
    }
    insert_sql = f"""
        INSERT INTO observations ({",".join(OBS_COLS)})
        VALUES ({",".join("?" * len(OBS_COLS))})
        ON CONFLICT(commodity, classification, market, date) DO UPDATE SET
          wholesale_price = COALESCE(excluded.wholesale_price, wholesale_price),
          retail_price    = COALESCE(excluded.retail_price, retail_price),
          supply_volume   = COALESCE(excluded.supply_volume, supply_volume),
          price_unit      = COALESCE(price_unit, excluded.price_unit),
          n_reports       = MAX(n_reports, excluded.n_reports)
    """
    rows = df[OBS_COLS].astype(object).where(pd.notna(df[OBS_COLS]), None)
    for row in rows.itertuples(index=False):
        key = (row.commodity, row.classification, row.market, row.date)
        if key not in existing:
            stats.inserted += 1
        else:
            old_w, old_r, old_v = existing[key]
            gains_value = (
                (old_w is None and row.wholesale_price is not None)
                or (old_r is None and row.retail_price is not None)
                or (old_v is None and row.supply_volume is not None)
            )
            if gains_value:
                stats.merged += 1
            else:
                stats.unchanged += 1
        old = existing.get(key, (None, None, None))
        existing[key] = (
            row.wholesale_price if row.wholesale_price is not None else old[0],
            row.retail_price if row.retail_price is not None else old[1],
            row.supply_volume if row.supply_volume is not None else old[2],
        )
        conn.execute(insert_sql, tuple(row))
    conn.commit()
    return stats


def log_ingest(conn: sqlite3.Connection, reports: list) -> None:
    for r in reports:
        d = r.to_dict()
        d["hit_row_cap"] = int(d["hit_row_cap"])
        cols = ",".join(d)
        conn.execute(
            f"INSERT INTO ingest_log ({cols}) VALUES ({','.join('?' * len(d))})",
            list(d.values()),
        )
    conn.commit()


def read_observations(conn: sqlite3.Connection, commodity: str | None = None) -> pd.DataFrame:
    q = "SELECT * FROM observations"
    params: tuple = ()
    if commodity:
        q += " WHERE commodity = ?"
        params = (commodity,)
    return pd.read_sql_query(q, conn, params=params)


def coverage_report(conn: sqlite3.Connection) -> pd.DataFrame:
    df = read_observations(conn)
    df["date"] = pd.to_datetime(df["date"])
    rows = []
    for (com, cls), g in df.groupby(["commodity", "classification"]):
        weeks = g["date"].dt.to_period("W").nunique()
        span_weeks = max(1, (g["date"].max() - g["date"].min()).days // 7 + 1)
        gaps = sorted(g["date"].unique())
        largest_gap = max(
            ((b - a).days for a, b in zip(gaps, gaps[1:])), default=0
        )
        rows.append({
            "commodity": com, "classification": cls,
            "date_min": g["date"].min().date(), "date_max": g["date"].max().date(),
            "distinct_weeks": weeks, "span_weeks": span_weeks,
            "week_coverage_pct": round(100 * weeks / span_weeks),
            "n_markets": g["market"].nunique(),
            "largest_gap_days": largest_gap,
            "n_rows": len(g),
        })
    return pd.DataFrame(rows).sort_values(["commodity", "classification"]).reset_index(drop=True)


def write_forecasts(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    cols = [
        "commodity", "classification", "market", "county", "as_of",
        "target_week_start", "horizon_weeks", "price_type",
        "p10", "p50", "p90", "unit", "last_price", "last_price_date",
        "tier", "confidence", "anomaly_flag", "anomaly_note", "sms_text",
    ]
    sub = df.reindex(columns=cols)
    rows = sub.astype(object).where(pd.notna(sub), None)
    conn.executemany(
        f"INSERT OR REPLACE INTO forecasts ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        rows.itertuples(index=False),
    )
    conn.commit()
