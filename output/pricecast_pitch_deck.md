# PriceCast Pitch Deck

---

## 1. PriceCast

**KAMIS farm price forecasts for smallholder farmers.**

PriceCast turns government market-price exports into weekly crop forecasts and plain-language SMS alerts for farmers in Kenya.

**Tagline:** Farmers deserve price foresight, not market rumors.

**Demo:** KAMIS Excel exports -> cleaned SQLite data -> weekly forecasts -> English/Kiswahili SMS.

---

## 2. The Problem

Smallholder farmers often sell without reliable forward price information.

- Market prices move by crop, market, and week.
- KAMIS has useful market data, but exports are raw, capped, duplicated, and hard to act on.
- Farmers need low-bandwidth answers, not dashboards.
- A bad forecast can be worse than no forecast, so trust matters.

**Core pain:** "Should I sell here this week, wait, or check another market?"

---

## 3. The Solution

PriceCast converts messy KAMIS exports into farmer-ready price guidance.

- Cleans and deduplicates KAMIS Excel files.
- Builds weekly commodity-market series.
- Forecasts 1, 2, and 4 weeks ahead.
- Uses confidence tiers so the system can say "not enough data."
- Generates SMS messages in plain English or Kiswahili with Claude, with deterministic fallback.

**Outcome:** A farmer gets a short message with expected price, range, trend, and confidence.

---

## 4. Product Flow

1. **Ingest:** Load KAMIS "Export to Excel" files.
2. **Clean:** Parse KES/Kg prices, normalize market names, dedupe overlaps.
3. **Model:** Build leakage-safe weekly features and train pooled LightGBM quantile models.
4. **Trust:** Compare against last-price and seasonal baselines; tier each series.
5. **Explain:** Turn validated forecast JSON into SMS-ready advice.
6. **Persist:** Store observations and forecasts in SQLite for API, USSD, SMS, and dashboard layers.

---

## 5. What Makes It Trustworthy

PriceCast is designed to avoid fake certainty.

- **Model tier:** Enough recent data and enough history for ML.
- **Seasonal fallback:** Some history, but not enough confidence for the model.
- **Insufficient data:** No prediction; point farmers to the nearest covered market.
- **Baseline gate:** The model must beat "last known price" in backtests.
- **Anomaly detection:** Flags unusually high or low prices versus county/national medians.
- **SMS validation:** Claude output must stay short and include the given forecast number.

---

## 6. Evidence From The Demo

Current demo database:

- **10,517** deduplicated market observations.
- **220** distinct markets.
- **372** commodity-market series.
- **1,116** forecast rows across 1, 2, and 4 week horizons.
- One-week tiers: **38 model**, **124 seasonal fallback**, **210 insufficient data**.
- Crops covered in demo: **Dry Maize, Dry Onions, Tomatoes, Cabbages**.

Backtest highlight:

- Dry Maize, 1-week forecast: **10.7% MAPE** vs **16.4%** for last-price baseline.
- That is about a **35% error reduction** against the simple baseline.

---

## 7. Example Forecast

**Dry Maize, White Maize - Ahero, Kisumu**

- Data through: **2026-07-25**
- Last price: **55.00 KES/Kg**
- Next week forecast: **53.01 KES/Kg**
- Forecast range: **50.20 - 58.56 KES/Kg**
- Confidence: **medium**

Example SMS:

> Ahero Dry Maize: now 55 KES/kg, expected about 53 KES/kg next week (50-59). Trend: falling.

---

## 8. AI Layer

Claude is used where it is strongest: language, not price invention.

- The model outputs structured numbers first.
- Claude receives only validated forecast fields.
- The prompt forbids invented prices, dates, and advice beyond the forecast.
- If the API key is missing or the response fails validation, PriceCast uses a deterministic template.
- Messages can be generated in English or Kiswahili.

**Design principle:** ML predicts; Claude explains.

---

## 9. Go-To-Market

Start where farmers already coordinate decisions.

- County agriculture offices and extension officers.
- Farmer cooperatives and producer groups.
- Grain, onion, tomato, and cabbage value-chain partners.
- SMS/USSD access through Africa's Talking.
- Dashboard/API access for counties, co-ops, buyers, and NGOs.

Business model options:

- Sponsored farmer SMS alerts.
- Paid dashboards for co-ops and county teams.
- Forecast API for agribusiness, insurers, and food-security partners.

---

## 10. Roadmap

Phase 1: Demo complete.

- Static KAMIS exports.
- Forecast table contract.
- Backtest, charts, report, and SMS layer.

Phase 2:

- Scheduled KAMIS ingestion.
- Africa's Talking USSD and SMS subscriptions.
- FastAPI endpoints for forecasts and history.
- County/co-op dashboard.
- Alias-table UI and data-quality monitoring.
- Retraining schedule and expanded crop coverage.

---

## 11. The Ask

For a pilot, PriceCast needs:

- Live or regularly refreshed KAMIS access.
- SMS credits and Africa's Talking shortcode setup.
- County or co-op partners for farmer testing.
- Feedback from extension officers on language and usefulness.
- Support to expand from demo crops to more staples and fresh produce.

**Close:** PriceCast helps farmers make better market decisions with data they can actually receive, understand, and trust.
