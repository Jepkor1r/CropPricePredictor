# PriceCast demo report

## File coverage (what each export actually contains)

| source_file          | commodity   |   n_rows_raw |   n_rows_after_agg | date_min   | date_max   |   n_distinct_dates |   n_markets |   pct_missing_wholesale |   pct_missing_retail |   pct_missing_volume |   n_unparseable_prices |   n_bad_dates | hit_row_cap   |
|:---------------------|:------------|-------------:|-------------------:|:-----------|:-----------|-------------------:|------------:|------------------------:|---------------------:|---------------------:|-----------------------:|--------------:|:--------------|
| Final_Cabbages.xls   | Cabbages    |         3000 |               2848 | 2024-08-25 | 2026-07-25 |                500 |          88 |                    18.2 |                  2.7 |                 18.6 |                      0 |             0 | True          |
| Final_Maize.xls      | Dry Maize   |         3000 |               2876 | 2024-09-11 | 2026-07-25 |                479 |          80 |                     9.6 |                  0.5 |                 37   |                      0 |             0 | True          |
| Final_Onions.xls     | Dry Onions  |         1848 |               1740 | 2005-02-01 | 2008-12-04 |                279 |          25 |                     0   |                100   |                100   |                      0 |             0 | False         |
| Final_Onions.xls.xls | Dry Onions  |         3000 |               2915 | 2024-08-27 | 2026-07-25 |                501 |          91 |                    15.5 |                  2.5 |                 17.1 |                      0 |             0 | True          |
| Final_Tomatoes.xls   | Tomatoes    |         3000 |               2818 | 2024-09-05 | 2026-07-25 |                490 |          89 |                    15.4 |                  5.8 |                 18.4 |                      0 |             0 | True          |

## Per-commodity coverage

| commodity   | classification    | date_min   | date_max   |   distinct_weeks |   span_weeks |   week_coverage_pct |   n_markets |   largest_gap_days |   n_rows |
|:------------|:------------------|:-----------|:-----------|-----------------:|-------------:|--------------------:|------------:|-------------------:|---------:|
| Cabbages    | -                 | 2024-08-25 | 2026-07-25 |               89 |          100 |                  89 |          88 |                 47 |     2848 |
| Dry Maize   | Mixed-Traditional | 2024-09-11 | 2026-07-21 |               75 |           97 |                  77 |          46 |                138 |      492 |
| Dry Maize   | White Maize       | 2024-09-11 | 2026-07-25 |               83 |           98 |                  85 |          74 |                 67 |     2107 |
| Dry Maize   | Yellow Maize      | 2024-09-11 | 2026-07-19 |               65 |           97 |                  67 |          11 |                221 |      277 |
| Dry Onions  | -                 | 2005-02-01 | 2026-07-25 |              155 |         1121 |                  14 |         107 |               5745 |     4655 |
| Tomatoes    | -                 | 2024-09-05 | 2026-07-25 |               87 |           99 |                  88 |          89 |                 65 |     2818 |

## Backtest (rolling-origin, MAPE %, skill = model/naive — <1.0 beats naive)

| commodity   |   horizon |   n |   mape_model |   mape_naive |   mape_seasonal |   skill_vs_naive |
|:------------|----------:|----:|-------------:|-------------:|----------------:|-----------------:|
| Cabbages    |         1 | 138 |         12   |         11.7 |            22.6 |             1.03 |
| Cabbages    |         2 | 125 |         14.9 |         15.8 |            25.8 |             0.94 |
| Cabbages    |         4 |  95 |         18.1 |         21.3 |            28.4 |             0.85 |
| Dry Maize   |         1 | 116 |          7.5 |         11.1 |            10.4 |             0.68 |
| Dry Maize   |         2 | 101 |          8.7 |          7.8 |            10.4 |             1.12 |
| Dry Maize   |         4 |  77 |          8.8 |         10.1 |            11   |             0.87 |
| Dry Onions  |         1 | 153 |         17.6 |         17.9 |            22.6 |             0.98 |
| Dry Onions  |         2 | 156 |         17.6 |         17.3 |            24.3 |             1.02 |
| Dry Onions  |         4 | 125 |         15.3 |         17.1 |            23.1 |             0.89 |
| Tomatoes    |         1 | 135 |         43.5 |         33   |            48.3 |             1.32 |
| Tomatoes    |         2 | 122 |         55.2 |         41.9 |            52.9 |             1.32 |
| Tomatoes    |         4 |  89 |         50.8 |         42.9 |            31.6 |             1.18 |

## Sample SMS messages

- **Gikomba / Dry Maize**: (see console)
- **Nakuru Wakulima / Dry Onions**: (see console)
- **Nairobi Wakulima / Tomatoes**: (see console)
- **Ahero / Dry Maize**: (see console)
- **Ahero / Cabbages**: (see console)
- **Akala / Cabbages**: (see console)

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