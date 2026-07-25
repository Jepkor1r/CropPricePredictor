# PriceCast demo report

## File coverage (what each export actually contains)

| source_file           | commodity   |   n_rows_raw |   n_rows_after_agg | date_min   | date_max   |   n_distinct_dates |   n_markets |   pct_missing_wholesale |   pct_missing_retail |   pct_missing_volume |   n_unparseable_prices |   n_bad_dates | hit_row_cap   |
|:----------------------|:------------|-------------:|-------------------:|:-----------|:-----------|-------------------:|------------:|------------------------:|---------------------:|---------------------:|-----------------------:|--------------:|:--------------|
| cabbages.xls          | Cabbages    |          180 |                180 | 2005-02-01 | 2005-03-23 |                 33 |          13 |                     0   |                100   |                100   |                      0 |             0 | False         |
| dryonion.xls          | Dry Onions  |         3000 |               2904 | 2021-09-12 | 2022-02-10 |                151 |         195 |                     9.9 |                  1   |                  9.7 |                      0 |             0 | True          |
| maize.xls             | Dry Maize   |         3000 |               2876 | 2024-09-11 | 2026-07-25 |                479 |          80 |                     9.6 |                  0.5 |                 37   |                      0 |             0 | True          |
| Market Price.xls      | Dry Maize   |         3000 |               2876 | 2024-09-11 | 2026-07-25 |                479 |          80 |                     9.6 |                  0.5 |                 37   |                      0 |             0 | True          |
| Market Prices (1).xls | Dry Maize   |          100 |                 96 | 2026-07-01 | 2026-07-25 |                 25 |          31 |                    15   |                  1   |                 37   |                      0 |             0 | False         |
| Market Prices.xls     | Dry Maize   |          100 |                 96 | 2026-07-01 | 2026-07-25 |                 25 |          31 |                    15   |                  1   |                 37   |                      0 |             0 | False         |
| onions-final.xls      | Dry Onions  |         1848 |               1740 | 2005-02-01 | 2008-12-04 |                279 |          25 |                     0   |                100   |                100   |                      0 |             0 | False         |
| Tomatoes.xls          | Tomatoes    |         3000 |               2817 | 2005-10-03 | 2011-01-27 |                387 |          27 |                     0   |                100   |                100   |                      0 |             0 | True          |

## Per-commodity coverage

| commodity   | classification    | date_min   | date_max   |   distinct_weeks |   span_weeks |   week_coverage_pct |   n_markets |   largest_gap_days |   n_rows |
|:------------|:------------------|:-----------|:-----------|-----------------:|-------------:|--------------------:|------------:|-------------------:|---------:|
| Cabbages    | -                 | 2005-02-01 | 2005-03-23 |                8 |            8 |                 100 |          13 |                  5 |      180 |
| Dry Maize   | Mixed-Traditional | 2024-09-11 | 2026-07-21 |               75 |           97 |                  77 |          46 |                138 |      492 |
| Dry Maize   | White Maize       | 2024-09-11 | 2026-07-25 |               83 |           98 |                  85 |          74 |                 67 |     2107 |
| Dry Maize   | Yellow Maize      | 2024-09-11 | 2026-07-19 |               65 |           97 |                  67 |          11 |                221 |      277 |
| Dry Onions  | -                 | 2005-02-01 | 2022-02-10 |               89 |          889 |                  10 |         201 |               4665 |     4644 |
| Tomatoes    | -                 | 2005-10-03 | 2011-01-27 |               88 |          278 |                  32 |          27 |                799 |     2817 |

## Backtest (rolling-origin, MAPE %, skill = model/naive - <1.0 beats naive)

| commodity   |   horizon |   n |   mape_model |   mape_naive |   mape_seasonal |   skill_vs_naive |
|:------------|----------:|----:|-------------:|-------------:|----------------:|-----------------:|
| Dry Maize   |         1 |  58 |         10.7 |         16.4 |            14.4 |             0.65 |
| Dry Maize   |         2 |  54 |         10.6 |          9   |            13.1 |             1.18 |
| Dry Maize   |         4 |  47 |         10.9 |         13.3 |            14   |             0.82 |
| Dry Onions  |         1 |  41 |       7020.9 |       7123   |          6864.5 |             0.99 |
| Dry Onions  |         2 |  37 |       7499.4 |       7290.4 |          6727.5 |             1.03 |
| Dry Onions  |         4 |  22 |         14.6 |         32.4 |            46.5 |             0.45 |
| Tomatoes    |         1 |  66 |         24.9 |         22.1 |            25.1 |             1.13 |
| Tomatoes    |         2 |  41 |         20.3 |         19.8 |            47.9 |             1.03 |
| Tomatoes    |         4 |  51 |         31.4 |         36.4 |            27.5 |             0.86 |

## Sample SMS messages

- **Gikomba / Dry Maize**: (see console)
- **Nakuru Wakulima / Dry Onions**: (see console)
- **Nairobi Wakulima / Tomatoes**: (see console)
- **Kongowea / Cabbages**: (see console)
- **Kibuye / Cabbages**: (see console)
- **Bondo / Cabbages**: (see console)

## Phase 2 (designed, not built)

Integration contract: the `forecasts` and `observations` tables in `data/kamis.db`.
Everything below is a pure read — nothing re-runs the model at request time.

- **API** (FastAPI, future `api.py`): `GET /commodities`, `GET /markets?commodity=&county=`,
  `GET /forecast?commodity=&market=&classification=` (returns the forecasts row incl. `sms_text`),
  `GET /history?commodity=&market=&weeks=12`.
- **USSD (Africa's Talking)**: webhook receiving `sessionId, phoneNumber, text`; menu flow
  crop -> county -> market -> forecast screen (menus built from the API); final screen is a trimmed `sms_text`.
- **SMS push**: on each ingest+forecast run, send updated `sms_text` to a `subscriptions` table
  (phone, commodity, market, language) via AT `SMS.send`.
- **Dashboard**: web app over the same API — coverage view from `ingest_log`, county price map,
  per-market forecast charts.
- Also phase 2: KAMIS scraping/scheduled ingestion, unit conversion beyond /Kg, alias-table UI,
  retraining schedule.