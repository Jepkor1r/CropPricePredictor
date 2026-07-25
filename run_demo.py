#!/usr/bin/env python
"""End-to-end demo: ingest KAMIS exports -> SQLite -> backtest -> forecasts ->
SMS messages + charts + report.md.

Usage: python run_demo.py [--raw-dir data/raw] [--no-sms] [--lang en|sw]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))


def configure_text_io() -> None:
    """Keep Windows consoles from failing on generated SMS punctuation."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


configure_text_io()

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from pricecast import backtest as BT
from pricecast import db as DB
from pricecast import explain as EX
from pricecast import forecast as FC
from pricecast import ingest as ING
from pricecast.features import SERIES_KEYS, build_weekly_panel

OUTPUT = Path("output")

# Showcase cards: (commodity, classification, market) or None entries are
# filled dynamically to guarantee every tier is demonstrated.
SHOWCASE = [
    ("Dry Maize", "White Maize", "Gikomba"),   # stale series — honesty path
    ("Dry Onions", "-", "Nakuru Wakulima"),
    ("Tomatoes", "-", "Nairobi Wakulima"),
    ("Cabbages", "-", "Kongowea"),
]


def hr(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default="data/raw", type=Path)
    ap.add_argument("--no-sms", action="store_true", help="skip Claude, use templates")
    ap.add_argument("--lang", default="en", choices=["en", "sw"])
    args = ap.parse_args()
    OUTPUT.mkdir(exist_ok=True)

    # ---- 1. Ingest -------------------------------------------------------
    hr("1. INGEST — per-file coverage (gaps are data, not assumptions)")
    obs, reports = ING.load_all(args.raw_dir, Path("market_aliases.csv"))
    report_df = pd.DataFrame([r.to_dict() for r in reports])
    print(report_df.to_string(index=False))

    cands = ING.alias_candidates(obs)
    if cands:
        print("\nPossible market-name duplicates (add to market_aliases.csv to merge):")
        for county, a, b in cands:
            print(f"  {county}: '{a}' vs '{b}'")

    conn = DB.connect()
    stats = DB.upsert_observations(conn, obs)
    DB.log_ingest(conn, reports)
    print(f"\nDB upsert: {stats.inserted} inserted, {stats.merged} merged, "
          f"{stats.unchanged} unchanged (dedup across overlapping exports)")

    hr("Per-commodity coverage")
    print(DB.coverage_report(conn).to_string(index=False))

    # ---- 2. Panel + backtest ---------------------------------------------
    hr("2. BACKTEST — rolling-origin, model vs 'last known price'")
    all_obs = DB.read_observations(conn)
    panel = build_weekly_panel(all_obs)
    metrics = BT.run_backtest(panel)
    if metrics.empty:
        print("No series long enough to backtest.")
        mape_lookup, skill_lookup = {}, {}
    else:
        print(metrics.to_string(index=False))
        metrics.to_csv(OUTPUT / "backtest_metrics.csv", index=False)
        mape_lookup = BT.commodity_mape_lookup(metrics)
        skill_lookup = BT.commodity_skill_lookup(metrics)
        losers = metrics[(metrics["horizon"] == 1) & (metrics["skill_vs_naive"] >= 1.0)]
        if len(losers):
            print("\nWARNING: model does NOT beat naive for:",
                  ", ".join(losers["commodity"]),
                  "- their forecasts fall back to seasonal baseline (confidence: low).")

    # ---- 3. Forecasts ------------------------------------------------------
    hr("3. FORECASTS — all series, written to data/kamis.db :: forecasts")
    fdf = FC.generate_forecasts(panel, mape_lookup)
    # honesty: demote 'model' tier commodities that lost to naive
    if not metrics.empty:
        lost = set(metrics[(metrics["horizon"] == 1) & (metrics["skill_vs_naive"] >= 1.0)]["commodity"])
        demote = fdf["commodity"].isin(lost) & (fdf["tier"] == "model")
        fdf.loc[demote, ["tier", "confidence"]] = ["seasonal_fallback", "low"]
    DB.write_forecasts(conn, fdf)
    print(f"{len(fdf)} forecast rows "
          f"({fdf[fdf.horizon_weeks == 1].tier.value_counts().to_dict()} series by tier)")

    # ---- 4. Showcase cards -------------------------------------------------
    hr("4. SHOWCASE FORECAST CARDS")
    cards = list(SHOWCASE)
    h1 = fdf[fdf["horizon_weeks"] == 1]
    covered_tiers = {
        t for com, cls, mkt in cards
        for t in h1[(h1["commodity"] == com) & (h1["classification"] == cls)
                    & (h1["market"] == mkt)]["tier"]
    }
    pools = [
        fdf[(fdf["anomaly_flag"] == 1) & (fdf["horizon_weeks"] == 1)],
        h1[h1["tier"] == "insufficient_data"],
    ]
    if "model" not in covered_tiers:
        pools.insert(0, h1[h1["tier"] == "model"].sort_values("confidence"))
    for pool in pools:
        if len(pool):
            r = pool.iloc[0]
            extra = (r["commodity"], r["classification"], r["market"])
            if extra not in cards:
                cards.append(extra)

    sms_rows = []
    for com, cls, mkt in cards:
        sel = fdf[(fdf["commodity"] == com) & (fdf["classification"] == cls)
                  & (fdf["market"] == mkt)].sort_values("horizon_weeks")
        if sel.empty:
            print(f"\n(no series found for {com}/{cls} @ {mkt})")
            continue
        print_card(sel, skill_lookup, panel)
        row1 = sel.iloc[0].to_dict()
        if row1["tier"] == "insufficient_data":
            row1["nearest_market"] = FC.nearest_covered_market(fdf, sel.iloc[0])
        sms_rows.append(row1)
        chart(panel, sel, OUTPUT)

    # ---- 5. SMS messages ---------------------------------------------------
    hr("5. FARMER SMS MESSAGES" + (" (template mode)" if args.no_sms else " (Claude Haiku)"))
    import os
    if not os.environ.get("ANTHROPIC_API_KEY") and not args.no_sms:
        print("ANTHROPIC_API_KEY not set — using deterministic templates.\n")
    for row in sms_rows:
        text = EX.fallback_template(row, args.lang) if args.no_sms else EX.sms_for(row, args.lang)
        key = f"{row['market']} / {row['commodity']}"
        print(f"  [{key}]  ({len(text)} chars)\n  -> {text}\n")
        conn.execute(
            "UPDATE forecasts SET sms_text=? WHERE commodity=? AND classification=? "
            "AND market=? AND horizon_weeks=1",
            (text, row["commodity"], row["classification"], row["market"]),
        )
    conn.commit()

    write_report(report_df, DB.coverage_report(conn), metrics, fdf, sms_rows)
    print(f"\nDone. Charts + report in {OUTPUT}/, data in data/kamis.db")


def print_card(sel: pd.DataFrame, skill_lookup: dict, panel: pd.DataFrame) -> None:
    r = sel.iloc[0]
    cls = f" ({r['classification']})" if r["classification"] != "-" else ""
    n_weeks = len(panel[
        (panel["commodity"] == r["commodity"]) & (panel["classification"] == r["classification"])
        & (panel["market"] == r["market"]) & panel["price"].notna()
    ])
    print(f"\n-- {r['commodity']}{cls} - {r['market']}, {r['county']} " + "-" * 20)
    print(f"   Data through {r['as_of']} | {n_weeks} weekly obs | tier: {r['tier']}")
    if r["tier"] == "insufficient_data":
        stale_weeks = (pd.Timestamp(r["as_of"]) - pd.Timestamp(r["last_price_date"])).days // 7
        if stale_weeks > 8:
            print(f"   No forecast: no recent data - last report {r['last_price_date']}, "
                  f"{stale_weeks} weeks before the commodity's latest data. Too stale to forecast.")
        else:
            print(f"   No forecast: only {n_weeks} weeks of history - not enough for a forecast.")
        return
    print(f"   Last {r['price_type']}: {r['last_price']} {r['unit']} ({r['last_price_date']})")
    for _, f in sel.iterrows():
        if f["p50"] is None or pd.isna(f["p50"]):
            continue
        label = "Next week " if f["horizon_weeks"] == 1 else f"In {f['horizon_weeks']} weeks"
        print(f"   {label}: {f['p50']:.2f} {f['unit']}  "
              f"(range {f['p10']:.2f} - {f['p90']:.2f}) | confidence: {f['confidence']}")
    skill = skill_lookup.get(r["commodity"])
    if skill is not None and r["tier"] == "model":
        verdict = f"beats last-price by {round((1 - skill) * 100)}%" if skill < 1 else "does NOT beat last-price"
        print(f"   vs naive baseline: skill {skill} ({verdict})")
    if r["anomaly_flag"]:
        print(f"   Warning: {r['anomaly_note']}")


def chart(panel: pd.DataFrame, sel: pd.DataFrame, outdir: Path) -> None:
    r = sel.iloc[0]
    hist = panel[
        (panel["commodity"] == r["commodity"]) & (panel["classification"] == r["classification"])
        & (panel["market"] == r["market"]) & panel["price"].notna()
    ].sort_values("week")
    if hist.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hist["week"], hist["price"], lw=1.2, color="#2563eb", label=f"weekly {r['price_type']}")
    ok = sel[sel["p50"].notna()]
    if len(ok):
        weeks = pd.to_datetime(ok["target_week_start"])
        ax.fill_between(weeks, ok["p10"], ok["p90"], alpha=0.25, color="#f59e0b",
                        label="forecast P10–P90")
        ax.plot(weeks, ok["p50"], "o-", color="#d97706", label="forecast P50")
        ax.axhline(r["last_price"], ls=":", color="#6b7280", lw=1, label="naive (last price)")
    cls = f" ({r['classification']})" if r["classification"] != "-" else ""
    ax.set_title(f"{r['commodity']}{cls} - {r['market']} | data through {r['as_of']}")
    ax.set_ylabel(r["unit"])
    ax.legend(fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    name = f"{r['commodity']}_{r['market']}".replace(" ", "_").replace("/", "-")
    fig.savefig(outdir / f"{name}.png", dpi=110)
    plt.close(fig)


def write_report(files: pd.DataFrame, coverage: pd.DataFrame, metrics: pd.DataFrame,
                 fdf: pd.DataFrame, sms_rows: list) -> None:
    lines = [
        "# PriceCast demo report", "",
        "## File coverage (what each export actually contains)", "",
        files.to_markdown(index=False), "",
        "## Per-commodity coverage", "",
        coverage.to_markdown(index=False), "",
        "## Backtest (rolling-origin, MAPE %, skill = model/naive - <1.0 beats naive)", "",
        metrics.to_markdown(index=False) if not metrics.empty else "_no series long enough_", "",
        "## Sample SMS messages", "",
    ]
    for row in sms_rows:
        lines.append(f"- **{row['market']} / {row['commodity']}**: {row.get('sms_text') or '(see console)'}")
    lines += [
        "", "## Phase 2 (designed, not built)", "",
        "Integration contract: the `forecasts` and `observations` tables in `data/kamis.db`.",
        "Everything below is a pure read — nothing re-runs the model at request time.", "",
        "- **API** (FastAPI, future `api.py`): `GET /commodities`, `GET /markets?commodity=&county=`,",
        "  `GET /forecast?commodity=&market=&classification=` (returns the forecasts row incl. `sms_text`),",
        "  `GET /history?commodity=&market=&weeks=12`.",
        "- **USSD (Africa's Talking)**: webhook receiving `sessionId, phoneNumber, text`; menu flow",
        "  crop -> county -> market -> forecast screen (menus built from the API); final screen is a trimmed `sms_text`.",
        "- **SMS push**: on each ingest+forecast run, send updated `sms_text` to a `subscriptions` table",
        "  (phone, commodity, market, language) via AT `SMS.send`.",
        "- **Dashboard**: web app over the same API — coverage view from `ingest_log`, county price map,",
        "  per-market forecast charts.",
        "- Also phase 2: KAMIS scraping/scheduled ingestion, unit conversion beyond /Kg, alias-table UI,",
        "  retraining schedule.",
    ]
    (OUTPUT / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
