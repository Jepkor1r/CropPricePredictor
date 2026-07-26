"""Load and clean KAMIS 'Export to Excel' files.

The exports are .xlsx archives despite their .xls extension, so openpyxl is
forced. Wholesale and retail for the same (market, date) often arrive as
separate rows, each with its own supply volume, so rows are aggregated onto the
full observation key.

What this layer guarantees downstream:
  * canonical county/market spellings (see names.py) — 'Uasin-Gishu' and
    'Kajiado Market' never create phantom series;
  * junk rows (KAMIS ships a literal 'test market') are dropped and counted;
  * every price carries both its quoted unit and, where a mass equivalence is
    known, a KES/kg value — units are converted, not discarded.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from . import quality
from . import units as U
from .config import ALIASES_PATH, JUNK_MARKETS, ROW_CAP
from .names import (
    canonical_commodity,
    canonical_county,
    canonical_market,
    is_junk_market,
    squash,
)

EXPECTED_COLUMNS = [
    "Commodity", "Classification", "Grade", "Sex", "Market",
    "Wholesale", "Retail", "Supply Volume", "County", "Date",
]
MISSING = {"-", "", "n/a", "na", "null", "nan"}

# LibreOffice writes '.~Name.xls' and Excel writes '~$Name.xls' beside an open
# workbook. Both match a '*.xls' glob and neither is a spreadsheet, so feeding
# one to openpyxl aborts the whole ingest. One is committed on the main branch
# (`data/raw/.~Final_Maize.xls`), so this is a live hazard, not a hypothetical.
TEMP_FILE_PREFIXES = (".", "~$")

KEY_COLS = ["commodity", "classification", "grade", "sex", "market", "county", "date"]


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
    n_junk_rows: int
    n_unconvertible_units: int
    hit_row_cap: bool

    def to_dict(self) -> dict:
        return asdict(self)


def parse_price(cell) -> tuple[float | None, str | None]:
    """'38.89/Kg' -> (38.89, 'Kg'); '3,200 / 90kg bag' -> (3200.0, 'Bag')."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return None, None
    text = squash(cell)
    if text.lower() in MISSING:
        return None, None
    if "/" not in text:
        return None, None
    amount, _, unit = text.partition("/")
    amount = amount.strip().replace(",", "").replace("KES", "").replace("Ksh", "").strip()
    try:
        value = float(amount)
    except ValueError:
        return None, None
    return value, U.normalize_unit(unit)


def load_aliases(path: Path | None = ALIASES_PATH) -> dict[str, str]:
    if path is None or not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {
            row["raw_name"]: row["canonical_name"]
            for row in csv.DictReader(f)
            if row.get("raw_name") and row.get("canonical_name")
        }


def load_export(
    path: Path, aliases: dict[str, str] | None = None
) -> tuple[pd.DataFrame, FileReport]:
    raw = pd.read_excel(path, engine="openpyxl", dtype=str)
    missing_cols = [c for c in EXPECTED_COLUMNS if c not in raw.columns]
    if missing_cols:
        raise ValueError(
            f"{path.name}: missing expected columns {missing_cols}; found {list(raw.columns)}"
        )

    n_raw = len(raw)
    df = pd.DataFrame(index=raw.index)
    df["commodity"] = raw["Commodity"].map(canonical_commodity)
    df["classification"] = raw["Classification"].map(lambda s: squash(s) or "-")
    df["grade"] = raw["Grade"].map(lambda s: squash(s) or "-")
    df["sex"] = raw["Sex"].map(lambda s: squash(s) or "-")
    df["market_raw"] = raw["Market"].map(squash)
    df["market"] = raw["Market"].map(lambda s: canonical_market(s, aliases))
    df["county"] = raw["County"].map(canonical_county)

    n_unparseable = 0
    parsed: dict[str, list] = {}
    for col in ("Wholesale", "Retail"):
        values, unit_names = [], []
        for cell in raw[col]:
            value, unit = parse_price(cell)
            if value is None and squash(cell).lower() not in MISSING:
                n_unparseable += 1
            values.append(value)
            unit_names.append(unit)
        parsed[col] = values
        parsed[col + "_unit"] = unit_names

    df["wholesale_price"] = parsed["Wholesale"]
    df["retail_price"] = parsed["Retail"]
    df["price_unit"] = [
        w or r for w, r in zip(parsed["Wholesale_unit"], parsed["Retail_unit"], strict=True)
    ]

    n_unconvertible = 0
    w_kg, r_kg, kg_per_unit, basis = [], [], [], []
    for commodity, unit, wholesale, retail in zip(
        df["commodity"], df["price_unit"], df["wholesale_price"], df["retail_price"],
        strict=True,
    ):
        conv_w = U.to_per_kg(wholesale, unit, commodity)
        conv_r = U.to_per_kg(retail, unit, commodity)
        best = conv_w if conv_w.ok else conv_r
        w_kg.append(conv_w.price_per_kg)
        r_kg.append(conv_r.price_per_kg)
        kg_per_unit.append(best.kg_equivalent)
        basis.append(best.basis)
        if unit and (wholesale is not None or retail is not None) and not best.ok:
            n_unconvertible += 1
    df["wholesale_per_kg"] = w_kg
    df["retail_per_kg"] = r_kg
    df["kg_per_unit"] = kg_per_unit
    df["unit_basis"] = basis

    df["supply_volume"] = pd.to_numeric(
        raw["Supply Volume"].map(lambda s: None if squash(s).lower() in MISSING else squash(s)),
        errors="coerce",
    )
    dates = pd.to_datetime(raw["Date"], errors="coerce", format="mixed", dayfirst=False)
    n_bad_dates = int(dates.isna().sum())
    df["date"] = dates.dt.strftime("%Y-%m-%d")

    junk_mask = [
        is_junk_market(m, c, JUNK_MARKETS) for m, c in zip(df["market"], df["county"], strict=True)
    ]
    n_junk = int(pd.Series(junk_mask).sum())
    df = df[~pd.Series(junk_mask, index=df.index)]
    df = df[df["date"].notna() & (df["commodity"] != "")].copy()
    df["source_file"] = path.name

    agg = aggregate_observations(df)
    report = FileReport(
        source_file=path.name,
        commodity=", ".join(sorted(agg["commodity"].unique())) if len(agg) else "?",
        n_rows_raw=n_raw,
        n_rows_after_agg=len(agg),
        date_min=agg["date"].min() if len(agg) else "",
        date_max=agg["date"].max() if len(agg) else "",
        n_distinct_dates=int(agg["date"].nunique()) if len(agg) else 0,
        n_markets=int(agg["market"].nunique()) if len(agg) else 0,
        pct_missing_wholesale=(
            round(100 * df["wholesale_price"].isna().mean(), 1) if len(df) else 0.0
        ),
        pct_missing_retail=round(100 * df["retail_price"].isna().mean(), 1) if len(df) else 0.0,
        pct_missing_volume=round(100 * df["supply_volume"].isna().mean(), 1) if len(df) else 0.0,
        n_unparseable_prices=n_unparseable,
        n_bad_dates=n_bad_dates,
        n_junk_rows=n_junk,
        n_unconvertible_units=n_unconvertible,
        hit_row_cap=n_raw >= ROW_CAP,
    )
    return agg, report


def aggregate_observations(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicate observation-key rows: prices average, volumes sum."""
    if df.empty:
        return df.assign(n_reports=pd.Series(dtype=int))
    return df.groupby(KEY_COLS, as_index=False).agg(
        market_raw=("market_raw", "first"),
        wholesale_price=("wholesale_price", "mean"),
        retail_price=("retail_price", "mean"),
        wholesale_per_kg=("wholesale_per_kg", "mean"),
        retail_per_kg=("retail_per_kg", "mean"),
        price_unit=("price_unit", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
        kg_per_unit=("kg_per_unit", "first"),
        unit_basis=("unit_basis", "first"),
        supply_volume=("supply_volume", lambda s: s.sum() if s.notna().any() else None),
        n_reports=("date", "size"),
        source_file=("source_file", "first"),
    )


def alias_candidates(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    """Market names in one county that differ only by punctuation/case/spacing.

    The ' Market' suffix is already normalised away, so anything surfacing here
    needs a human decision, recorded in market_aliases.csv.
    """
    pairs = []
    for county, group in df.groupby("county"):
        by_stem: dict[str, list[str]] = {}
        for name in sorted(group["market"].unique()):
            stem = "".join(ch for ch in name.lower() if ch.isalnum())
            by_stem.setdefault(stem, []).append(name)
        for variants in by_stem.values():
            if len(variants) > 1:
                pairs.append((county, variants[0], variants[1]))
    return pairs


def discover_exports(raw_dir: Path) -> tuple[list[Path], list[Path]]:
    """Split a raw directory into (loadable exports, skipped editor lock files).

    Returned rather than printed so the caller decides how to report it and the
    library stays free of side effects.
    """
    candidates = sorted(
        set(Path(raw_dir).glob("*.xls")) | set(Path(raw_dir).glob("*.xlsx"))
    )
    usable, skipped = [], []
    for path in candidates:
        if path.name.startswith(TEMP_FILE_PREFIXES):
            skipped.append(path)
        else:
            usable.append(path)
    return usable, skipped


def load_all(
    raw_dir: Path, aliases_path: Path | None = ALIASES_PATH, screen: bool = True
) -> tuple[pd.DataFrame, list[FileReport]]:
    """Load every export in `raw_dir` and screen implausible prices across the whole set.

    Screening runs after concatenation on purpose: a single small export does
    not contain enough of a commodity to establish what "typical" means.

    Editor lock files are skipped by name. Anything else that fails to parse
    raises: silently skipping a file that was meant to be data is how coverage
    gaps get mistaken for market gaps.
    """
    aliases = load_aliases(aliases_path)
    frames, reports = [], []
    files, _skipped = discover_exports(raw_dir)
    if not files:
        raise FileNotFoundError(f"no readable .xls/.xlsx files in {raw_dir}")
    for path in files:
        try:
            agg, report = load_export(path, aliases)
        except Exception as exc:
            raise RuntimeError(
                f"failed to read {path.name}: {exc}. If this is an editor lock file or "
                "a partial download, remove it from data/raw/; otherwise re-export it "
                "from KAMIS."
            ) from exc
        frames.append(agg)
        reports.append(report)
    combined = pd.concat(frames, ignore_index=True)
    if screen:
        flags, reasons = quality.flag_implausible(combined)
        combined["quality_flag"] = flags
        combined["quality_reason"] = reasons
    else:
        combined["quality_flag"] = 0
        combined["quality_reason"] = None
    return combined, reports
