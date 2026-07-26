"""Command line entry points: end-to-end demo, USSD simulator, API server, SMS push."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import pandas as pd

from . import backtest as BT
from . import db as DB
from . import explain as EX
from . import forecast as FC
from . import geo
from . import ingest as ING
from . import prices as PR
from . import quality as QC
from . import sms as SMS
from . import ussd as USSD
from .config import DB_PATH, OUTPUT_DIR, PILOT_CROPS, RAW_DIR
from .features import build_weekly_panel

BAR = "=" * 74


def hr(title: str) -> None:
    print(f"\n{BAR}\n{title}\n{BAR}")


# --------------------------------------------------------------------------- demo
def cmd_demo(args: argparse.Namespace) -> None:
    import matplotlib

    matplotlib.use("Agg")

    OUTPUT_DIR.mkdir(exist_ok=True)
    conn = DB.connect(args.db)

    # 1. ingest ---------------------------------------------------------------
    hr("1. INGEST - per-file coverage (gaps are data, not assumptions)")
    _usable, skipped = ING.discover_exports(args.raw_dir)
    if skipped:
        print(f"Skipped {len(skipped)} editor lock file(s): "
              f"{', '.join(p.name for p in skipped)}\n")
    obs, reports = ING.load_all(args.raw_dir)
    report_df = pd.DataFrame([r.to_dict() for r in reports])
    print(report_df.drop(columns=["date_min", "date_max"]).to_string(index=False))
    print(f"\nDate ranges: {report_df['date_min'].min()} .. {report_df['date_max'].max()}")

    candidates = ING.alias_candidates(obs)
    if candidates:
        print("\nPossible duplicate market names (add to market_aliases.csv):")
        for county, a, b in candidates[:10]:
            print(f"  {county}: '{a}' vs '{b}'")

    screened = QC.screening_summary(obs)
    if not screened.empty:
        print(
            f"\nPlausibility screen: {int(obs['quality_flag'].sum())} of {len(obs)} rows "
            "flagged as data-entry errors (kept in the DB, excluded from prices/models):"
        )
        print(screened.to_string(index=False))

    stats = DB.upsert_observations(conn, obs)
    DB.log_ingest(conn, reports)
    print(
        f"\nDB upsert: {stats.inserted} inserted, {stats.merged} merged, "
        f"{stats.unchanged} unchanged (re-ingesting overlapping exports is a no-op)"
    )

    hr("2. COVERAGE - what we actually hold, per commodity")
    coverage = DB.coverage_report(conn)
    print(coverage.to_string(index=False))

    all_obs = DB.read_observations(conn)
    market_pairs = list(zip(all_obs["county"], all_obs["market"], strict=True))
    geo_stats = geo.coverage_stats(market_pairs)
    print(
        f"\nGeo registry: {geo_stats['with_coordinates']}/{geo_stats['markets']} markets "
        f"({geo_stats['pct']}%) have coordinates; the rest fall back to county centroids."
    )

    # 2. freshness ------------------------------------------------------------
    hr("3. FRESHNESS GATE - staleness is judged against today, not the extract")
    today = pd.Timestamp.today().normalize()
    fresh = (
        all_obs.assign(date=pd.to_datetime(all_obs["date"]))
        .groupby("commodity")["date"].max()
        .rename("last_seen").reset_index()
    )
    fresh["days_old"] = (today - fresh["last_seen"]).dt.days
    fresh["servable"] = fresh["days_old"] <= PR.DEFAULT_MAX_AGE_DAYS
    fresh["last_seen"] = fresh["last_seen"].dt.date
    print(fresh.to_string(index=False))
    stale = fresh[~fresh["servable"]]["commodity"].tolist()
    if stale:
        print(
            f"\n  {', '.join(stale)}: too old to serve to a farmer today. "
            "The live product would show nothing here rather than a stale number."
        )

    # 3. panel + backtest -----------------------------------------------------
    hr("4. BACKTEST - rolling-origin, model vs 'last known price'")
    panel = build_weekly_panel(all_obs, verbose=True)
    metrics = BT.run_backtest(panel)
    mape_lookup: dict[str, float] = {}
    losers: set[str] = set()
    if metrics.empty:
        print("No series long enough to backtest.")
    else:
        print(metrics.to_string(index=False))
        metrics.to_csv(OUTPUT_DIR / "backtest_metrics.csv", index=False)
        mape_lookup = BT.commodity_mape_lookup(metrics)
        losers = BT.losing_commodities(metrics)
        if losers:
            print(
                f"\n  HONESTY GATE: {', '.join(sorted(losers))} do not beat the naive "
                "baseline at h=1. Their model output is suppressed entirely and replaced "
                "with last-price + an empirical band."
            )

    # 4. forecasts ------------------------------------------------------------
    hr(f"5. FORECASTS (as_of mode: {args.as_of}) - written with their vintage")
    forecasts = FC.generate_forecasts(
        panel, mape_lookup, as_of_mode=args.as_of, suppress_model_for=losers
    )
    if args.as_of == "per_commodity":
        print(
            "  WARNING: as_of=per_commodity treats each extract's last week as 'now'. "
            "Useful to exercise the model on historical crops; never ship it.\n"
        )
    DB.write_forecasts(conn, forecasts)
    if not forecasts.empty:
        horizon1 = forecasts[forecasts["horizon_weeks"] == 1]
        print(f"{len(forecasts)} rows across {len(horizon1)} series")
        print(horizon1.groupby(["tier", "method"]).size().rename("series").to_string())

    # 5. the actual product ---------------------------------------------------
    hr("6. PRICE CARDS - the product: nearby prices + itemised farm-gate floor")
    shown = 0
    for crop in PILOT_CROPS:
        commodity = crop["commodity"]
        for county in crop["counties"]:
            card = PR.price_card(conn, commodity, county, limit=3,
                                 reference_date=args.reference_date)
            if not card.markets:
                continue
            print_card(card)
            shown += 1
            break
    if not shown:
        print(
            "No pilot crop has prices fresh enough to serve today.\n"
            "Re-run with --reference-date YYYY-MM-DD to demo against the extract's own era, "
            "e.g. --reference-date 2026-07-25"
        )

    # 6. USSD walk-through ----------------------------------------------------
    hr("7. USSD SESSION (exactly what Africa's Talking would exchange)")
    demo_ussd_session(conn, args.reference_date)

    # 7. SMS ------------------------------------------------------------------
    hr("8. SMS OUTBOX")
    outbox = SMS.outbox(conn, limit=5)
    if outbox.empty:
        print("(no messages)")
    else:
        print(outbox.to_string(index=False))
    if not SMS.configured():
        print("\nAT_USERNAME / AT_API_KEY not set - messages are queued dry-run, not sent.")

    # 8. impact ---------------------------------------------------------------
    hr("9. FARM-GATE REPORTS - the moat dataset")
    gap = DB.farm_gate_gap(conn)
    print(gap.to_string(index=False) if not gap.empty else "(no farmer reports yet)")

    charts(panel, forecasts, OUTPUT_DIR)
    write_report(report_df, coverage, metrics, forecasts, geo_stats, fresh)
    print(f"\nDone. Charts + report in {OUTPUT_DIR}/, data in {args.db}")
    conn.close()


def print_card(card) -> None:
    print(f"\n-- {card.commodity} for a farmer in {card.origin_county} "
          f"(as of {card.as_of}) " + "-" * 12)
    for market in card.markets:
        distance = f"{market.distance_km:>5.0f} km" if market.distance_km else "   ? km"
        trend = f", {market.trend_label}" if market.trend_label != "unknown" else ""
        print(
            f"   {market.market:<22} {distance}  {market.price_kes_per_kg:>7.2f} KES/kg  "
            f"({market.days_old}d old{trend})"
        )
    floor = card.floor
    if floor:
        print(f"\n   Wholesale at {floor['market']}: {floor['wholesale_kes_per_kg']:.2f} KES/kg")
        for component in floor["components"]:
            print(f"     - {component['name']:<32} "
                  f"{component['low']:>6.2f} - {component['high']:>6.2f}   {component['detail']}")
        print(f"     = FARM-GATE FLOOR: {floor['floor_low']:.2f} - {floor['floor_high']:.2f} "
              f"KES/kg  ({floor['deductions_pct_of_wholesale']}% of wholesale is cost)")
    for warning in card.warnings:
        print(f"   ! {warning}")
    print(f"\n   SMS: {EX.card_sms(card)}")


def demo_ussd_session(conn: sqlite3.Connection, reference_date: str | None) -> None:
    app = USSD.UssdApp(conn, reference_date=reference_date)
    phone = "+254700000001"
    script = ["", "1", "1*1", "1*1*1"]
    text = ""
    for text in script:
        response = app.handle(phone, text)
        print(f"\n  farmer sends text={text!r}")
        for line in response.render().splitlines():
            print(f"    | {line}")
        if response.close:
            return
    # continue into the price screen actions if the session is still open
    for follow_up in (f"{text}*1", f"{text}*2", f"{text}*2*18"):
        response = app.handle(phone, follow_up)
        print(f"\n  farmer sends text={follow_up!r}")
        for line in response.render().splitlines():
            print(f"    | {line}")
        if response.close and follow_up.endswith("18"):
            break


def charts(panel: pd.DataFrame, forecasts: pd.DataFrame, outdir: Path) -> None:
    import matplotlib.pyplot as plt

    # clear stale charts so the directory always reflects the current run
    for old in outdir.glob("*.png"):
        old.unlink()
    if panel.empty or forecasts.empty:
        return
    horizon1 = forecasts[(forecasts["horizon_weeks"] == 1) & forecasts["p50"].notna()]
    # model-tier series first, then a spread across commodities
    horizon1 = horizon1.sort_values(
        ["tier", "n_weekly_obs"], ascending=[True, False]
    ).head(6)
    for _, row in horizon1.iterrows():
        history = panel[
            (panel["commodity"] == row["commodity"])
            & (panel["market"] == row["market"])
            & (panel["county"] == row["county"])
            & panel["price"].notna()
        ].sort_values("week")
        if history.empty:
            continue
        series = forecasts[
            (forecasts["commodity"] == row["commodity"])
            & (forecasts["market"] == row["market"])
            & (forecasts["county"] == row["county"])
            & forecasts["p50"].notna()
        ].sort_values("horizon_weeks")
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(history["week"], history["price"], lw=1.2, color="#2563eb",
                label=f"weekly {row['price_type']}")
        weeks = pd.to_datetime(series["target_week_start"])
        ax.fill_between(weeks, series["p10"], series["p90"], alpha=0.25,
                        color="#f59e0b", label="P10-P90")
        ax.plot(weeks, series["p50"], "o-", color="#d97706", label="P50")
        ax.axhline(row["last_price"], ls=":", color="#6b7280", lw=1, label="naive (last price)")
        ax.set_title(f"{row['commodity']} - {row['market']}, {row['county']} "
                     f"({row['tier']}/{row['method']})")
        ax.set_ylabel(row["unit"])
        ax.legend(fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        name = f"{row['commodity']}_{row['market']}".replace(" ", "_").replace("/", "-")
        fig.savefig(outdir / f"{name}.png", dpi=110)
        plt.close(fig)


def write_report(files: pd.DataFrame, coverage: pd.DataFrame, metrics: pd.DataFrame,
                 forecasts: pd.DataFrame, geo_stats: dict, fresh: pd.DataFrame) -> None:
    lines = [
        "# PriceCast run report", "",
        "## 1. File coverage (what each export actually contains)", "",
        files.to_markdown(index=False), "",
        "## 2. Per-commodity coverage", "",
        coverage.to_markdown(index=False), "",
        f"Geo registry: {geo_stats['with_coordinates']}/{geo_stats['markets']} markets "
        f"({geo_stats['pct']}%) have coordinates.", "",
        "## 3. Freshness gate (vs wall-clock today)", "",
        fresh.to_markdown(index=False), "",
        "## 4. Backtest (MAPE %, skill = model/naive; <1.0 means the model may speak)", "",
        metrics.to_markdown(index=False) if not metrics.empty else "_no series long enough_", "",
        "## 5. Forecast tiers", "",
    ]
    if not forecasts.empty:
        horizon1 = forecasts[forecasts["horizon_weeks"] == 1]
        lines.append(
            horizon1.groupby(["tier", "method"]).size().rename("series").to_frame()
            .to_markdown()
        )
    (OUTPUT_DIR / "report.md").write_text("\n".join(lines))


# --------------------------------------------------------------------------- ussd
def cmd_ussd(args: argparse.Namespace) -> None:
    """Interactive offline USSD simulator - no telco account, no network."""
    conn = DB.connect(args.db)
    app = USSD.UssdApp(conn, reference_date=args.reference_date)
    phone = args.phone
    text = ""
    print(f"USSD simulator - dialling {args.service_code} as {phone}")
    print("(type a menu number and press enter; Ctrl-C to quit)\n")
    while True:
        response = app.handle(phone, text)
        body = response.render()
        print("-" * 40)
        print(body)
        print("-" * 40)
        if response.close:
            break
        try:
            entry = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        text = entry if not text else f"{text}*{entry}"
    conn.close()


# --------------------------------------------------------------------------- serve
def cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn
    except ModuleNotFoundError:
        sys.exit("uvicorn is not installed. Run:  pip install '.[api]'")
    uvicorn.run("pricecast.api:app", host=args.host, port=args.port, reload=args.reload)


# --------------------------------------------------------------------------- push
def cmd_push(args: argparse.Namespace) -> None:
    conn = DB.connect(args.db)
    results = SMS.push_to_subscribers(
        conn, reference_date=args.reference_date, use_llm=args.llm, limit=args.limit
    )
    if not results:
        print("No active subscriptions.")
    for result in results:
        print(f"[{result.status}] {result.phone}: {result.message}")
    conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pricecast")
    parser.add_argument("--db", default=str(DB_PATH), type=Path)
    sub = parser.add_subparsers(dest="command")

    demo = sub.add_parser("demo", help="end-to-end pipeline demo")
    demo.add_argument("--raw-dir", default=RAW_DIR, type=Path)
    demo.add_argument("--as-of", default="today", choices=["today", "per_commodity"],
                      help="'today' is the honest production setting")
    demo.add_argument("--reference-date", default=None,
                      help="pretend today is this date (demo against historical extracts)")
    demo.set_defaults(func=cmd_demo)

    ussd_cmd = sub.add_parser("ussd", help="interactive offline USSD simulator")
    ussd_cmd.add_argument("--phone", default="+254700000001")
    ussd_cmd.add_argument("--service-code", default="*384*7890#")
    ussd_cmd.add_argument("--reference-date", default=None)
    ussd_cmd.set_defaults(func=cmd_ussd)

    serve = sub.add_parser("serve", help="run the FastAPI app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    push = sub.add_parser("push", help="send price SMS to subscribers")
    push.add_argument("--reference-date", default=None)
    push.add_argument("--limit", type=int, default=None)
    push.add_argument("--llm", action="store_true", help="phrase messages with Claude")
    push.set_defaults(func=cmd_push)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args = parser.parse_args((argv or []) + ["demo"])
    args.func(args)


if __name__ == "__main__":
    main()
