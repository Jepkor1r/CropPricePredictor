# PriceCast

**Know what your crop is worth before the broker tells you.**

A Kenyan smallholder negotiates against someone who knows yesterday's terminal
price, today's transport rate and the county cess. PriceCast closes that gap on
a feature phone: the prices actually paid at the markets near you in the last
few days, plus an itemised farm-gate floor once transport, cess, handling and
spoilage come out.

Data: KAMIS (`kamis.kilimo.go.ke`) exports, augmented with EPRA diesel prices, a
curated market geo-registry, packaging conversions and county cess schedules.

- Rationale, architecture and roadmap: [`docs/SOLUTION_DESIGN.md`](docs/SOLUTION_DESIGN.md)
- Pitch deck: [`docs/pitch_deck.md`](docs/pitch_deck.md)

## Quick start

```bash
uv venv .venv
uv pip install -r requirements-dev.txt --python .venv/bin/python
uv pip install -e . --no-deps --python .venv/bin/python     # installs the `pricecast` command

.venv/bin/pricecast demo     # full pipeline: ingest -> screen -> backtest -> cards -> USSD
.venv/bin/pricecast ussd     # interactive USSD simulator (offline, no telco account)
.venv/bin/pricecast serve    # FastAPI at http://127.0.0.1:8000/docs
.venv/bin/python -m pytest -q
```

`python run_demo.py` still works and is equivalent to `pricecast demo`.
Add `--as-of per_commodity` to exercise the model against the historical
extracts (it warns loudly; never ship it).

## Coverage today

| Crop | Current data | Markets | Servable |
|---|---|---|---|
| Dry Maize | 2024-09 → 2026-07 | 80 | yes |
| Dry Onions | 2024-08 → 2026-07 | 91 | yes |
| Tomatoes | 2024-09 → 2026-07 | 89 | yes |
| Cabbages | 2024-08 → 2026-07 | 88 | yes |
| Red Irish potato | — | — | **no export yet** |

19,094 observations · 221 markets · 46 counties · 100% of observed markets
geocoded. Historical extracts (2005–2011 tomatoes/cabbages, 2005–2008 and
2021–2022 onions) are retained: they deepen the pooled model and backtest
without ever being served as current prices.

## What the demo shows

1. **Ingest** — per-file coverage, so gaps are visible instead of assumed away;
   editor lock files are skipped by name, real corruption fails loudly.
2. **Plausibility screen** — KAMIS contains real typos (prices from 0.01 to
   8,000 KES/kg on crops with 20–60 medians). 178 rows flagged, kept for audit,
   excluded from anything a farmer sees.
3. **Freshness gate** — staleness is measured against *today*, and 52-week
   coverage (not whole-span) decides serviceability.
4. **Backtest** — rolling-origin, model vs "last known price". A commodity's
   model output is suppressed unless it wins.
5. **Price cards** — nearest markets, distances, ages, trend, and the itemised
   farm-gate floor with a source on every line. The floor is never anchored on
   a price older than 7 days, and says so when it rejects a stale higher quote.
6. **USSD session** — exactly the payloads Africa's Talking would exchange.
7. **SMS outbox** — dry-run unless AT credentials are present.
8. **Farm-gate reports** — offers farmers report back, versus the wholesale
   reference. The dataset nobody else has.

## Interfaces

| Surface | Entry point |
|---|---|
| USSD (Africa's Talking) | `POST /ussd`, or `pricecast.cli ussd` offline |
| SMS push | `pricecast.cli push` (dry-run without credentials) |
| HTTP API | `/card`, `/netback`, `/prices/latest`, `/forecast`, `/history`, `/reports`, `/impact` |
| Batch | `run_demo.py` / `pricecast.cli demo` |

Nothing on the request path trains a model or calls an LLM — USSD has a ~5 s
telco timeout. Forecasts are computed in batch and read back.

## Layout

```
src/pricecast/
  config.py    # paths, pilot scope, tunable constants
  names.py     # canonical county/market/commodity spellings
  units.py     # unit normalisation + conversion to KES/kg
  quality.py   # plausibility screen (flag, never delete)
  ingest.py    # KAMIS .xls parsing -> observation rows
  db.py        # SQLite schema v2 + all reads/writes
  registry.py  # loaders for data/registry/*.csv
  geo.py       # market coordinates, haversine, nearest-N
  netback.py   # itemised farm-gate floor
  prices.py    # the product core: nearby prices + floor
  features.py  # weekly panel, leakage-safe features
  model.py     # LightGBM quantile + naive-with-band fallback
  backtest.py  # rolling-origin skill vs naive
  forecast.py  # vintaged forecasts with honest tiers
  explain.py   # SMS templates (+ optional Claude phrasing)
  ussd.py      # menu state machine (pure, testable)
  sms.py       # Africa's Talking, dry-run outbox by default
  api.py       # FastAPI read layer
  cli.py       # demo / ussd / serve / push
data/registry/ # units, packaging, markets_geo, county_centroids,
               # transport_rates, cess, spoilage, fuel_prices
```

## Operating it

**Adding data.** Drop more KAMIS exports into `data/raw/` and re-run. Exports
cap at 3000 rows — pull per-crop in contiguous, slightly overlapping date
chunks; if a file has exactly 3000 rows the range was truncated, so halve it and
re-export. Overlaps dedupe automatically; re-ingesting the same file is a no-op.

Naming convention: `Final_<Crop>.xls` for current-era exports (add an era
suffix when a crop has several, e.g. `Final_Onions_2024-2026.xls`) and
`Historical_<Crop>_<years>.xls` for older ones. All four current files sit at
the 3000-row cap, so each still has internal gaps worth back-filling.

Close the workbook before running: LibreOffice/Excel leave `.~Name.xls` and
`~$Name.xls` lock files that match a `*.xls` glob. Those are skipped and
reported; anything else unreadable stops the run rather than silently
shrinking your coverage.

**Monthly.** Update `data/registry/fuel_prices.csv` from the EPRA gazette. It is
the only manual input the netback engine needs.

**Before a pilot.** Every row in `data/registry/cess.csv` is marked INDICATIVE.
Verify against the actual County Finance Act for your pilot counties — the
system surfaces that warning to the user until you do.

**Schema.** The raw exports are the source of truth. If the schema version
changes, delete `data/kamis.db` and re-run; the connection refuses to write new
rows into an old file rather than corrupting keys.

## Forecast tiers

| Tier | Meaning |
|---|---|
| `model` | ≥26 weekly observations, fresh, and the commodity beat naive in backtest |
| `naive_fallback` | Last price + an empirical band from that series' own volatility |
| `insufficient_data` | Too thin or too stale — the system declines and points to the nearest covered market |

## Configuration

```
ANTHROPIC_API_KEY=   # optional: Claude phrasing for push SMS (templates otherwise)
AT_USERNAME=         # optional: Africa's Talking; without it SMS is dry-run
AT_API_KEY=
AT_SENDER_ID=
```
