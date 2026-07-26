# PriceCast frontend

Next.js 16 (App Router, Turbopack) landing page and dashboard for the PriceCast
forecasting pipeline. Apple-influenced layout, green theme, light and dark modes.

## Run it

```bash
npm install
npm run data     # export the pipeline's SQLite output to public/data/*.json
npm run dev      # http://localhost:3000
```

`npm run data` runs `../scripts/export_frontend_data.py` against `../data/kamis.db`,
so run the Python pipeline (`python run_demo.py`) at least once first. The export
is tolerant of schema drift — the optional `backtest_mape` and `skill_vs_naive`
columns are picked up when the pipeline records them and skipped when it doesn't.

## Routes

| Route | What it shows |
|---|---|
| `/` | Landing page — the problem, the pipeline, honest accuracy, SMS delivery |
| `/login` | Unauthenticated by design; the button routes straight to the dashboard |
| `/dashboard` | KPIs, backtest small multiples, tier breakdown, anomalies |
| `/dashboard/forecasts` | Filterable series explorer with forecast cone and SMS preview |
| `/dashboard/accuracy` | Where the model beats the naive baseline and where it doesn't |
| `/dashboard/coverage` | Per-file ingest report and per-crop reporting coverage |
| `/dashboard/messages` | The farmer-facing messages Claude generated |

## Charts

Charts follow the project's data-visualisation standard rather than ad-hoc taste:

- **Palette** — a green-led categorical order (green, blue, orange, aqua, yellow,
  magenta, violet, red) chosen by enumerating every green-first ordering and
  keeping only those that pass the colour-vision gates in both modes. Worst
  adjacent CVD ΔE is 9.1 light / 8.4 dark against a target of 8; worst
  normal-vision ΔE is 19.6 / 19.3 against a floor of 15. **The slot order is the
  colourblind-safety mechanism — reordering it silently breaks that guarantee.**
- On the light surface slots 4–6 sit below 3:1 contrast, so any chart using them
  must ship visible labels or the table view.
- **Every chart has a table view.** A value must never be reachable only by
  hovering.
- Confidence uses a validated ordinal green ramp because it is an ordered scale,
  not a status. Anomalies use the reserved status palette and always carry an
  icon and a text label, never colour alone.
- Coverage bars are one hue: colouring nominal bars by their own value would
  re-encode bar length as hue.
- Price charts do not anchor the y-axis at zero — price is a level, not a
  magnitude growing from a baseline. Bars still grow from zero.

Tokens live in `src/app/globals.css`; both modes are declared under the OS media
query and the `data-theme` toggle scope so the toggle wins either way.
