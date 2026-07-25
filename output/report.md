# PriceCast demo report

## File coverage (what each export actually contains)

| source_file           | commodity   |   n_rows_raw |   n_rows_after_agg | date_min   | date_max   |   n_distinct_dates |   n_markets |   pct_missing_wholesale |   pct_missing_retail |   pct_missing_volume |   n_unparseable_prices |   n_bad_dates | hit_row_cap   |
|:----------------------|:------------|-------------:|-------------------:|:-----------|:-----------|-------------------:|------------:|------------------------:|---------------------:|---------------------:|-----------------------:|--------------:|:--------------|
| Market Price.xls      | Dry Maize   |         3000 |               2876 | 2024-09-11 | 2026-07-25 |                479 |          80 |                     9.6 |                  0.5 |                 37   |                      0 |             0 | True          |
| Market Prices (1).xls | Dry Maize   |          100 |                 96 | 2026-07-01 | 2026-07-25 |                 25 |          31 |                    15   |                  1   |                 37   |                      0 |             0 | False         |
| Market Prices.xls     | Dry Maize   |          100 |                 96 | 2026-07-01 | 2026-07-25 |                 25 |          31 |                    15   |                  1   |                 37   |                      0 |             0 | False         |
| Tomatoes.xls          | Tomatoes    |         3000 |               2817 | 2005-10-03 | 2011-01-27 |                387 |          27 |                     0   |                100   |                100   |                      0 |             0 | True          |
| cabbages.xls          | Cabbages    |          180 |                180 | 2005-02-01 | 2005-03-23 |                 33 |          13 |                     0   |                100   |                100   |                      0 |             0 | False         |
| dryonion.xls          | Dry Onions  |         3000 |               2904 | 2021-09-12 | 2022-02-10 |                151 |         195 |                     9.9 |                  1   |                  9.7 |                      0 |             0 | True          |
| maize.xls             | Dry Maize   |         3000 |               2876 | 2024-09-11 | 2026-07-25 |                479 |          80 |                     9.6 |                  0.5 |                 37   |                      0 |             0 | True          |

## Per-commodity coverage

| commodity   | classification    | date_min   | date_max   |   distinct_weeks |   span_weeks |   week_coverage_pct |   n_markets |   largest_gap_days |   n_rows |
|:------------|:------------------|:-----------|:-----------|-----------------:|-------------:|--------------------:|------------:|-------------------:|---------:|
| Cabbages    | -                 | 2005-02-01 | 2005-03-23 |                8 |            8 |                 100 |          13 |                  5 |      180 |
| Dry Maize   | Mixed-Traditional | 2024-09-11 | 2026-07-21 |               75 |           97 |                  77 |          46 |                138 |      492 |
| Dry Maize   | White Maize       | 2024-09-11 | 2026-07-25 |               83 |           98 |                  85 |          74 |                 67 |     2107 |
| Dry Maize   | Yellow Maize      | 2024-09-11 | 2026-07-19 |               65 |           97 |                  67 |          11 |                221 |      277 |
| Dry Onions  | -                 | 2021-09-12 | 2022-02-10 |               23 |           22 |                 105 |         195 |                  2 |     2904 |
| Tomatoes    | -                 | 2005-10-03 | 2011-01-27 |               88 |          278 |                  32 |          27 |                799 |     2817 |

## Backtest (rolling-origin, MAPE %, skill = model/naive — <1.0 beats naive)

| commodity   |   horizon |   n |   mape_model |   mape_naive |   mape_seasonal |   skill_vs_naive |
|:------------|----------:|----:|-------------:|-------------:|----------------:|-----------------:|
| Dry Maize   |         1 | 116 |          7.6 |         10.4 |            10.4 |             0.73 |
| Dry Maize   |         2 |  97 |          7.6 |          7.1 |            10.1 |             1.07 |
| Dry Maize   |         4 |  78 |          9.8 |         11.2 |            11.6 |             0.88 |
| Tomatoes    |         1 |  63 |         27.2 |         23.5 |            43.9 |             1.16 |
| Tomatoes    |         2 | 100 |         31.1 |         30.1 |            39   |             1.03 |
| Tomatoes    |         4 |  44 |         21.3 |         25.3 |            48.8 |             0.84 |

## Sample SMS messages

- **Gikomba / Dry Maize**: (see console)
- **Nakuru Wakulima / Dry Onions**: (see console)
- **Nairobi Wakulima / Tomatoes**: (see console)
- **Kongowea / Cabbages**: (see console)
- **Ahero / Dry Maize**: (see console)
- **Kibuye / Cabbages**: (see console)
- **Bondo / Cabbages**: (see console)

## Phase 2 (designed, not built)

Integration contract: the `forecasts` and `observations` tables in `data/kamis.db`.
Everything below is a pure read — nothing re-runs the model at request time.

- **API** (FastAPI, future `api.py`): `GET /commodities`, `GET /markets?commodity=&county=`,
  `GET /forecast?commodity=&market=&classification=` (returns the forecasts row incl. `sms_text`),
  `GET /history?commodity=&market=&weeks=12`.
- **USSD (Africa's Talking)**: webhook receiving `sessionId, phoneNumber, text`; menu flow
  crop → county → market → forecast screen (menus built from the API); final screen is a trimmed `sms_text`.
- **SMS push**: on each ingest+forecast run, send updated `sms_text` to a `subscriptions` table
  (phone, commodity, market, language) via AT `SMS.send`.
- **Dashboard**: web app over the same API — coverage view from `ingest_log`, county price map,
  per-market forecast charts.
- Also phase 2: KAMIS scraping/scheduled ingestion, unit conversion beyond /Kg, alias-table UI,
  retraining schedule.