# PriceCast Pitch Deck

> Structure adapted from the team's original deck; narrative and figures
> updated to the shipped v2 system (price transparency + farm-gate floor).
> All numbers are from the current `run_demo.py` run and are reproducible.

---

## 1. PriceCast

**Know what your crop is worth before the broker tells you.**

PriceCast turns Kenyan government market-price data into a farm-gate answer a
smallholder can act on, delivered on a feature phone.

**Tagline:** The broker knows the price. Now so do you.

**Demo:** KAMIS exports → screened price database → nearby market prices +
itemised farm-gate floor → USSD/SMS in English or Kiswahili.

---

## 2. The Problem

A farmer negotiates against someone who knows strictly more than they do.

- The broker knows yesterday's terminal price, today's transport rate, and the
  county cess. The farmer knows none of it.
- Fresh produce is perishable, so waiting for a better offer has a deadline.
- Farmers need answers on a feature phone, not a dashboard.
- The gap is not *forecasting*. It is **information asymmetry, today**.

**Core pain:** "This broker is offering me 18 a kilo. Is that fair, or am I
being robbed?"

---

## 3. The Solution

Three answers, in order of how much we can defend them:

| Layer | What it says | Confidence |
|---|---|---|
| **Observed prices** | "Mogogosiek paid 54 KES/kg five days ago" | Fact, from government data |
| **Farm-gate floor** | "After transport, cess, handling and spoilage, your floor is 47–51" | Ranged, itemised, every line cited |
| **Forecast** | "Next week ≈ X" | Only shown where it beats the naive baseline |

Most agritech leads with the forecast, which is the least trustworthy layer.
We lead with what we can prove and gate the rest.

---

## 4. Product Flow

1. **Ingest:** KAMIS "Export to Excel" files; lock files skipped, corruption
   fails loudly.
2. **Screen:** canonicalise counties/markets, convert packaging units to
   KES/kg, flag implausible prices.
3. **Locate:** rank markets by road distance from the farmer's county.
4. **Net back:** wholesale − transport − cess − handling − spoilage, as a band.
5. **Gate:** forecasts only where backtested skill beats last-known-price.
6. **Deliver:** USSD menu, SMS, or API — no model or LLM on the request path.
7. **Learn:** capture what the broker actually offered.

---

## 5. What Makes It Trustworthy

Designed so the system cannot quietly mislead a farmer:

- **Freshness gate:** crops with no recent quote are not offered at all. Stale
  data is worse than no data in a negotiation.
- **Fresh-anchor rule:** the floor is never based on a price older than 7 days,
  even if that stale price is the highest nearby — and the card names the quote
  it rejected.
- **Plausibility screen:** 178 of 19,094 rows are enumerator typos (0.01 to
  8,000 KES/kg on crops with 20–60 medians). Flagged, retained for audit,
  never served.
- **Skill gate:** a crop's model is suppressed entirely unless it beats
  "last known price" in a rolling-origin backtest.
- **Marginal-route warning:** when costs exceed ~40% of the price, we say
  hauling may not be worth it.
- **Cited deductions:** every line of the floor carries its source, and
  indicative cess rates are labelled as such.

---

## 6. Evidence From The Demo

Current database:

- **19,094** screened observations · **221** markets · **46** counties.
- **4 crops live today:** Dry Maize, Dry Onions, Tomatoes, Cabbages
  (all current through **2026-07-25**).
- **1,644** forecast rows; at one week: **55 model**, **107 naive fallback**,
  **386 declined for insufficient/stale data**.
- **100%** of observed markets geocoded.
- **115** automated tests, lint clean.

Backtest, one week ahead (MAPE vs naive baseline):

| Crop | Model | Naive | Verdict |
|---|---|---|---|
| Dry Maize | 9.7% | 15.5% | model speaks (37% better) |
| Cabbages | 13.3% | 13.6% | model speaks (marginal) |
| Dry Onions | 11.7% | 10.0% | **suppressed** — naive wins |
| Tomatoes | 29.0% | 22.9% | **suppressed** — naive wins |

Half our crops lose to the naive baseline, and the system says so rather than
dressing up a worse prediction.

---

## 7. Example: What A Farmer Gets

**Cabbages, farmer in Nyandarua**

```
Kagio    91 km   10 KES/kg  (6d old)
Mukuyu   86 km   35 KES/kg  (15d old - too stale to anchor)
Kutus   101 km   15 KES/kg  (9d old)

Floor at Kagio: 2.52 - 6.37 KES/kg
  transport   1.45-3.04   cess 0.88-1.34
  handling    0.30-0.60   spoilage 1.00-2.50
Costs eat ~56% of the price - a nearer market or holding may net you more.
```

That last line is the product. A glut has made the haul uneconomic, and the
farmer learns it before loading a lorry.

---

## 8. AI Layer

Claude is used where it is strongest: language, not price invention.

- Arithmetic and gating happen first, deterministically.
- Claude receives only validated fields and may not invent prices or advice.
- Output is validated against the underlying numbers; failure falls back to a
  deterministic template.
- **Nothing on the USSD path calls an LLM** — a ~5 second telco timeout and
  per-session cost make that a non-starter.

**Design principle:** the system computes; Claude only phrases.

---

## 9. The Moat

KAMIS records what *markets* paid. Nobody systematically records **what brokers
offered at the farm gate.**

Every USSD session asks. Each answer is stored against the wholesale reference
and the computed floor, and `/impact` reports the gap. In the demo a reported
18 KES/kg offer sat **67% below** the wholesale reference.

That dataset calibrates our own netback model, and it is the evidence base for
the entire thesis — the thing no competitor can copy by scraping.

---

## 10. Go-To-Market

Start where farmers already coordinate decisions.

- County agriculture offices and extension officers.
- Farmer cooperatives and producer groups.
- Maize, onion, tomato and cabbage value-chain partners.
- SMS/USSD via Africa's Talking; API/dashboard for institutions.

**Business model:** free to farmers. A KES 2,500–4,500/month farmer
subscription is not viable for someone whose whole bag of maize is worth ~4,500.
Revenue is B2B — co-ops, counties, NGOs, insurers and lenders pricing credit
risk — with the farm-gate gap dataset as the differentiated asset.

---

## 11. Roadmap

**Built:** ingest + screening, geo registry, netback engine, price service,
USSD, SMS, REST API, forecast gating, farm-gate capture, 115 tests.

**Next:** scheduled KAMIS ingestion (the one remaining single point of
fragility); Red Irish potato export; verify cess against county Finance Acts;
Africa's Talking production shortcode; field-calibrate the floor against
reported offers.

**Later:** OSRM routing, Postgres + PostGIS, WhatsApp/IVR, weather-driven glut
early warning, buyer network so price discovery becomes price realisation.

---

## 12. The Ask

- Regularly refreshed KAMIS access (or a data-sharing MOU).
- SMS credits and an Africa's Talking shortcode.
- One county or co-op partner for farmer testing.
- Extension-officer feedback on language and usefulness.
- Introductions to a buyer or insurer for the B2B revenue path.

**Close:** Farmers do not need a crystal ball. They need to walk into the
negotiation knowing what their crop is worth — and to know when we do not know.
