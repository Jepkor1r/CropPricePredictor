# PriceCast — KAMIS farm price forecasts for smallholder farmers

Demo pipeline: static KAMIS "Export to Excel" files → cleaned SQLite dataset →
weekly price forecasts per commodity+market → plain-language farmer SMS
(Claude Haiku), with an honest backtest against "last known price".

## Run it

```bash
uv venv .venv && uv pip install -r requirements.txt --python .venv/bin/python
.venv/bin/python run_demo.py            # Claude SMS if a key is in .env
.venv/bin/python run_demo.py --no-sms   # deterministic template SMS
.venv/bin/python run_demo.py --lang sw  # Kiswahili messages
```

Outputs: console coverage/backtest/forecast cards, charts + `report.md` in
`output/`, and everything persisted in `data/kamis.db` (the `forecasts` table
is the integration contract for the Phase-2 USSD/SMS/dashboard layers).

API key: put `ANTHROPIC_API_KEY=...` (or `CLAUDE_API_KEY=...`) in `.env`.
Without it the demo still runs end-to-end using template messages.

## Adding more data

Drop more KAMIS exports into `data/raw/` and re-run. Exports are capped at
3000 rows — pull per-crop, working backwards in contiguous (slightly
overlapping) date-range chunks; if a file has exactly 3000 rows the range was
truncated, so halve it and re-export. Overlaps dedupe automatically. The
per-file coverage table printed at ingest shows exactly what each file
contains, so gaps are visible rather than assumed away.

## Layout

```
src/pricecast/
  ingest.py    # .xls(x) parsing, "NN.NN/Kg" → float, ' - ' → NULL, aggregation
  db.py        # SQLite: observations (upsert/dedup), ingest_log, forecasts
  features.py  # weekly panel, scale-invariant target, leakage-safe features
  model.py     # naive/seasonal baselines, pooled LightGBM quantile models, tiering
  backtest.py  # rolling-origin eval, MAPE + skill vs naive
  forecast.py  # per-series forecasts + deterministic anomaly detection
  explain.py   # Claude Haiku SMS layer (validated, template fallback)
run_demo.py    # end-to-end entry point
```

Forecast tiers: `model` (≥26 weekly obs, fresh data, and the commodity beat
the naive baseline in backtest), `seasonal_fallback` (8–25 obs, low
confidence), `insufficient_data` (too little or too stale — the SMS points to
the nearest covered market instead of guessing).
