# PriceCast — Solution Design

**Problem.** A Kenyan smallholder negotiates with a broker who knows yesterday's
terminal-market price, the current transport rate, and the county cess. The
farmer knows none of it. That asymmetry, not the absence of a forecast, is what
transfers margin from producer to middleman.

**Product.** Tell the farmer, before the broker arrives: *what this crop
actually fetched at the markets near me in the last few days, and what a
defensible floor is once transport, cess, handling and spoilage come out* —
delivered on a feature phone.

---

## 1. The reframe that drives everything

The first version of this repo was a price **forecasting** engine. That is the
hardest, least trustworthy, and lowest-marginal-value part of the problem, and
its own backtest said so: the model lost to "last known price" for tomatoes at
one week ahead. A farmer standing in the yard does not primarily need next
month's price; they need today's price and a floor they can argue from.

So the architecture inverts the priority:

| Layer | Claim it makes | Can it be wrong? |
|---|---|---|
| **Observed prices** (core) | "Mogogosiek paid 54 KES/kg five days ago" | Only if the data is wrong |
| **Netback floor** (differentiator) | "After costs, your floor is ~47–51" | Ranged and itemised, with sources |
| **Forecast** (enrichment) | "Next week ≈ X" | Yes — so it is gated on beating naive |

Forecasting is retained, but it only speaks where a rolling-origin backtest
shows it beats the naive baseline. Everywhere else the system says last price
plus an empirical band, and labels it as such.

---

## 2. Architecture

```
data/raw/*.xls  (manual KAMIS exports, overlapping chunks)
        │
        ▼
   ingest.py ── names.py (canonical county/market)
        │     ── units.py + registry/packaging.csv (convert, don't drop)
        │     ── quality.py (plausibility screen: flag, never delete)
        ▼
   SQLite (schema v2): observations · forecasts (vintaged) · subscriptions
                       farm_gate_reports · query_log · sms_outbox · ingest_log
        │
        ├── BATCH ─────────────────────────────────────────────
        │   features.py → model.py → backtest.py → forecast.py
        │   (LightGBM quantile, pooled; suppressed unless skill < 1)
        │
        └── REQUEST PATH (no model, no LLM) ────────────────────
            prices.py  ── geo.py (nearest markets, haversine × circuity)
                       ── netback.py (itemised floor from registries)
                   │
            ┌──────┼───────────────┬──────────────┐
          ussd.py  api.py        sms.py        cli.py
        (AT webhook + offline simulator, dry-run outbox)
```

**Hard rule:** nothing on the request path trains a model or calls an LLM.
USSD has a ~5 s telco timeout, and per-screen LLM calls would wreck both latency
and unit economics. Every farmer-facing string is either a template or a
precomputed `sms_text`.

---

## 3. Pilot scope

Ranked by feasibility (does KAMIS actually report it now?) × broker pain.

| # | Crop | Farm-side counties | Terminal markets | Why |
|---|---|---|---|---|
| 1 | Dry Maize | Uasin Gishu, Trans Nzoia | Eldoret, Kitale, Nairobi | Only crop with current data in-repo (2024-09 → 2026-07, 80 markets) |
| 2 | Red Irish potato | Nyandarua, Nakuru | Nairobi Wakulima | Extended-bag exploitation is the flagship national issue; registry already encodes 50 kg vs 110 kg |
| 3 | Dry Onions | Kajiado, Bungoma | Nairobi, Nakuru Wakulima | 198 markets in-repo; Tegemeo TR31 gives a netback calibration benchmark |
| 4 | Tomatoes | Kirinyaga, Kajiado | Nairobi Wakulima | Perishability makes price info urgent; showcases the honest fallback |
| 5 | Cabbages | Nyandarua, Meru | Nairobi Wakulima, Kongowea | Strong Nyandarua→Nairobi corridor story |

Crops 2–5 need fresh exports; only maize is currently servable, and the system
says so out loud rather than quoting 2011 prices.

---

## 4. Data augmentation map

**Tier 0 — nothing works without these (all free)**

| Data | Source | Status |
|---|---|---|
| Daily KAMIS prices | kamis.kilimo.go.ke | Manual exports today; scraper is the single highest-value next step |
| Market geo-registry | OSM + manual curation | **Built** — 182/217 observed markets (83.9%) have coordinates |
| Packaging → kg table | KAMIS/AFA conventions | **Built** — `registry/packaging.csv` |

**Tier 1 — high value, easy**

| Data | Source | Status |
|---|---|---|
| EPRA monthly diesel | EPRA gazette | **Wired** — `registry/fuel_prices.csv`, indexes all transport costs |
| Road distance | OSRM (self-host) or Google | Approximated by haversine × 1.30 circuity; `geo.road_distance_km` is the single swap point |
| WFP/HDX Kenya prices | HDX | Not yet — cross-validation and gap-filling |
| Weather / rainfall | Open-Meteo, CHIRPS | Not yet — glut early warning |

**Tier 2 — valuable, medium effort**

| Data | Source | Status |
|---|---|---|
| County cess schedules | County Finance Acts | **Skeleton built** for 10 counties, every row flagged INDICATIVE until verified |
| RATIN cross-border flows | Eastern Africa Grain Council | Not yet — Busia/Malaba maize shocks |
| **Farm-gate offers** | **Our own USSD** | **Built** — `farm_gate_reports` |

That last row is the moat. KAMIS records what markets paid; nobody
systematically records **what brokers offered at the farm gate**. Every USSD
session asks, stores the offer against the wholesale reference and the computed
floor, and `/impact` reports the gap. That dataset both calibrates the netback
model and is the evidence base for the whole thesis.

---

## 5. Netback model

```
floor = wholesale − transport − cess(origin) − cess(market) − handling − spoilage
```

Design rules, in priority order:

1. **Never a single number.** Every deduction is a low/high range with a cited
   source; the output is a band. A fake-precise "KES 43.20" gets laughed at by a
   broker and the farmer never trusts the service again.
2. **Transport rates are hire rates**, so they already contain the transporter's
   margin — no separate margin line, which would double-count.
3. **Diesel-indexed**, not fixed: only the fuel share (~38%, CAK 2019) moves with
   the EPRA pump price, off a reference rate card.
4. **Cess is charged twice** in practice — leaving the producing county and
   entering the terminal market — so both are modelled.
5. **Uneconomic routes are flagged**, not shown as a negative price.

Calibration check (in the test suite): Tegemeo TR31 measured onions
Naroosura→Nairobi, 260 km, at ~KES 2.5/kg in the mid-2000s. Escalated to today's
diesel, a 7 t lorry should land in roughly 4–9 KES/kg. The rate card produces
4.13–8.67. Worked example, Trans Nzoia → Nairobi Wakulima at 50 KES/kg wholesale:

```
transport   425 km, lorry_7t              6.74 – 14.16
cess (origin) Trans Nzoia                 0.33 –  0.56
cess/levy (market) Nairobi                0.22 –  0.56
handling & market brokerage (3–6%)        1.50 –  3.00
spoilage in transit (1–3%, cereal)        0.50 –  1.50
                                       ─────────────────
FARM-GATE FLOOR                          30.22 – 40.71   (29% of wholesale is cost)
```

---

## 6. Honesty mechanisms (the part that makes it defensible)

These are deliberate product features, not caveats:

- **Freshness gate.** Staleness is measured against wall-clock today. Crops
  whose newest quote is from 2011 are not listed in the USSD menu at all —
  offering them would dead-end the farmer after they had spent airtime.
- **Plausibility screen.** KAMIS contains real typos: Dry Onions at 0.02 KES/kg
  (Gakoromone) and 2,100 KES/kg (Sibanga) against a ~50 median. 87 of 13,581
  rows are flagged. They stay in the database with a reason and are excluded
  from prices and models. This alone took the onion backtest from a nonsense
  7019% MAPE to 14.9%.
- **Skill gate.** A commodity's model output is suppressed entirely unless it
  beat naive at h=1, and the suppressed series are re-forecast with the fallback
  so the label and the numbers always agree.
- **Vintaged forecasts.** `as_of` is part of the forecasts primary key, so
  "what did you tell farmers three weeks ago, and were you right?" is answerable.
- **Provenance on every number.** Distance precision (`market` vs
  `county_centroid`), cess marked INDICATIVE, unverified market coordinates —
  all surfaced as warnings rather than hidden.

---

## 7. What v1 got wrong, and what changed

| v1 defect | Consequence | Fix |
|---|---|---|
| `county` absent from the observation key | Markets sharing a name in different counties silently merged into one price series | County (and grade/sex) in the primary key and in `SERIES_KEYS` |
| Non-modal units dropped silently | Fatal at 270 commodities with bags/crates/nets/trays | `units.py` + `packaging.csv` convert to KES/kg; unconvertible rows counted and reported |
| Demotion kept model numbers under a fallback label | Rows whose tier and content disagreed | Suppressed series are re-forecast with `naive_band` |
| Fallback was the seasonal mean | Fell back to a *worse* predictor (tomatoes: seasonal 43.9 vs naive 23.5 MAPE) | Fallback is last-price + empirical band |
| Cross-market medians mixed wholesale and retail | Feature encoded price-type noise, not geography | Medians computed within `price_type` |
| `nearest_covered_market` returned the first row | Not nearest by any definition; no distance existed anywhere | Real geo registry + haversine ranking |
| Staleness measured per-commodity | A 2011 extract looked "fresh" and was forecast as current | Wall-clock gate, `per_commodity` is opt-in and warns |
| Forecast rows overwritten on re-run | No accuracy audit possible | `as_of` in the primary key |
| No plausibility screening | 0.02 KES/kg onions served as real prices | `quality.py` |
| No tests, no packaging | Parser regressions silent | 102 tests, ruff clean, `pyproject.toml` |

---

## 8. Roadmap

**Phase 0 (done).** Schema v2, canonicalisation, unit conversion, plausibility
screen, geo registry, netback v0, API, USSD, SMS, tests.

**Phase 1 — make it live.** KAMIS scraper on a daily cron with append-only raw
snapshots (the single highest-value remaining item); Africa's Talking sandbox →
production shortcode; fresh exports for pilot crops 2–5; verify cess against
actual Finance Acts for the pilot counties.

**Phase 2 — earn trust at the farm gate.** Field-test the floor estimate against
reported offers; recalibrate transport/handling from `farm_gate_reports`; swap
haversine for OSRM; add WFP/RATIN cross-checks.

**Phase 3 — scale.** Postgres + PostGIS once concurrent USSD load arrives;
WhatsApp/IVR; weather-driven glut early warning; buyer network so price
discovery becomes price *realisation*.

**Monetisation.** Free to farmers. The research brief's KES 2,500–4,500/month
farmer subscription is not viable for a smallholder whose entire bag of maize is
worth ~4,500. Revenue comes B2B: co-ops, county governments, NGOs, insurers and
lenders doing credit risk — the Esoko path — with the farm-gate gap dataset as
the asset nobody else has.

**KPIs.** Median data age per served market (< 3 days); % pilot markets covered;
farmer-reported offer vs wholesale gap (target: measurable narrowing); USSD
repeat-usage rate; per-series forecast skill where deployed.
