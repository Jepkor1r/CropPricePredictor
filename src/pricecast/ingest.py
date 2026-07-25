"""Load and clean KAMIS 'Export to Excel' files.

The exports are .xlsx archives despite their .xls extension, so we force the
openpyxl engine. Wholesale and retail for the same (market, date) often arrive
as separate rows, each with its own supply volume — aggregation collapses them.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, asdict
from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = [
    "Commodity", "Classification", "Grade", "Sex", "Market",
    "Wholesale", "Retail", "Supply Volume", "County", "Date",
]
ROW_CAP = 3000  # KAMIS export truncates at this many rows
MISSING = {"-", ""}
_PRICE_RE = re.compile(r"^([\d,]+(?:\.\d+)?)\s*/\s*(\w+)$")
_WS_RE = re.compile(r"\s+")

KEY_COLS = ["commodity", "classification", "market", "date"]


@dataclass
class FileReport:
    source_file: str
    commodity: str
    n_rows_raw: int
    n_rows_after_agg: int
    date_min: str
    date_max: str
    n_distinct_dates: int
    n_markets: int
    pct_missing_wholesale: float
    pct_missing_retail: float
    pct_missing_volume: float
    n_unparseable_prices: int
    n_bad_dates: int
    hit_row_cap: bool

    def to_dict(self) -> dict:
        return asdict(self)


def parse_price(cell) -> tuple[float | None, str | None]:
    """'38.89/Kg' -> (38.89, 'Kg'); ' - ', '-', '', NaN -> (None, None)."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return None, None
    s = str(cell).strip()
    if s in MISSING:
        return None, None
    m = _PRICE_RE.match(s)
    if not m:
        return None, None
    return float(m.group(1).replace(",", "")), m.group(2)


def load_aliases(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    with open(path, newline="") as f:
        return {row["raw_name"]: row["canonical_name"]
                for row in csv.DictReader(f) if row.get("canonical_name")}


def normalize_name(s, aliases: dict[str, str] | None = None) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = _WS_RE.sub(" ", str(s).strip())
    if aliases and s in aliases:
        s = aliases[s]
    return s


def load_export(path: Path, aliases: dict[str, str] | None = None) -> tuple[pd.DataFrame, FileReport]:
    """Read one export into per-report long rows (pre-aggregation) + its report."""
    raw = pd.read_excel(path, engine="openpyxl", dtype=str)
    missing_cols = [c for c in EXPECTED_COLUMNS if c not in raw.columns]
    if missing_cols:
        raise ValueError(
            f"{path.name}: missing expected columns {missing_cols}; found {list(raw.columns)}"
        )

    n_raw = len(raw)
    df = pd.DataFrame()
    df["commodity"] = raw["Commodity"].map(lambda s: normalize_name(s))
    df["classification"] = raw["Classification"].map(
        lambda s: normalize_name(s) or "-"
    )
    df["market_raw"] = raw["Market"].map(lambda s: normalize_name(s))
    df["market"] = raw["Market"].map(lambda s: normalize_name(s, aliases))
    df["county"] = raw["County"].map(lambda s: normalize_name(s))

    n_unparseable = 0

    def _price(col):
        nonlocal n_unparseable
        vals, units = [], []
        for cell in raw[col]:
            v, u = parse_price(cell)
            if v is None and str(cell).strip() not in MISSING and not pd.isna(cell):
                n_unparseable += 1
            vals.append(v)
            units.append(u)
        return vals, units

    df["wholesale_price"], w_units = _price("Wholesale")
    df["retail_price"], r_units = _price("Retail")
    df["price_unit"] = [w or r for w, r in zip(w_units, r_units)]
    df["supply_volume"] = pd.to_numeric(
        raw["Supply Volume"].map(lambda s: None if s is None or str(s).strip() in MISSING else s),
        errors="coerce",
    )
    dates = pd.to_datetime(raw["Date"], errors="coerce")
    n_bad_dates = int(dates.isna().sum())
    df["date"] = dates.dt.strftime("%Y-%m-%d")

    df = df[df["date"].notna() & (df["market"] != "")].copy()
    df["source_file"] = path.name

    agg = aggregate_observations(df)
    report = FileReport(
        source_file=path.name,
        commodity=", ".join(sorted(agg["commodity"].unique())) if len(agg) else "?",
        n_rows_raw=n_raw,
        n_rows_after_agg=len(agg),
        date_min=agg["date"].min() if len(agg) else "",
        date_max=agg["date"].max() if len(agg) else "",
        n_distinct_dates=agg["date"].nunique(),
        n_markets=agg["market"].nunique(),
        pct_missing_wholesale=round(100 * df["wholesale_price"].isna().mean(), 1) if len(df) else 0.0,
        pct_missing_retail=round(100 * df["retail_price"].isna().mean(), 1) if len(df) else 0.0,
        pct_missing_volume=round(100 * df["supply_volume"].isna().mean(), 1) if len(df) else 0.0,
        n_unparseable_prices=n_unparseable,
        n_bad_dates=n_bad_dates,
        hit_row_cap=n_raw >= ROW_CAP,
    )
    return agg, report


def aggregate_observations(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicate (commodity, classification, market, date) rows.

    Prices average across the day's submissions; volumes sum (each row is a
    separate submission); n_reports counts the collapsed rows.
    """
    if df.empty:
        return df.assign(n_reports=pd.Series(dtype=int))
    return (
        df.groupby(KEY_COLS, as_index=False)
        .agg(
            county=("county", "first"),
            market_raw=("market_raw", "first"),
            wholesale_price=("wholesale_price", "mean"),
            retail_price=("retail_price", "mean"),
            price_unit=("price_unit", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
            supply_volume=("supply_volume", lambda s: s.sum() if s.notna().any() else None),
            n_reports=("date", "size"),
            source_file=("source_file", "first"),
        )
    )


def alias_candidates(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Pairs of market names in the same county equal after dropping ' Market'."""
    pairs = []
    for county, grp in df.groupby("county"):
        names = sorted(grp["market"].unique())
        by_stem: dict[str, list[str]] = {}
        for n in names:
            stem = re.sub(r"\s+Market$", "", n, flags=re.IGNORECASE).lower()
            by_stem.setdefault(stem, []).append(n)
        for stem, variants in by_stem.items():
            if len(variants) > 1:
                pairs.append((county, variants[0], variants[1]))
    return pairs


def load_all(raw_dir: Path, aliases_path: Path | None = None) -> tuple[pd.DataFrame, list[FileReport]]:
    aliases = load_aliases(aliases_path)
    frames, reports = [], []
    files = sorted(list(raw_dir.glob("*.xls")) + list(raw_dir.glob("*.xlsx")))
    if not files:
        raise FileNotFoundError(f"no .xls/.xlsx files in {raw_dir}")
    for path in files:
        agg, report = load_export(path, aliases)
        frames.append(agg)
        reports.append(report)
    return pd.concat(frames, ignore_index=True), reports
