"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS, ChartFrame, GRID, TooltipCard, type SeriesKey } from "./ChartFrame";
import { kes, monthDate, shortDate } from "@/lib/format";
import type { Forecast, HistoryPoint } from "@/lib/types";

type Row = {
  week: string;
  actual?: number | null;
  forecast?: number | null;
  /** A [low, high] pair renders as a range area — unlike a stacked pair it
   *  doesn't drag the y-domain down to zero. */
  band?: [number, number] | null;
  p10?: number | null;
  p90?: number | null;
};

/**
 * One market's weekly price with its forecast cone.
 *
 * Two series, so a legend is present. The band is the same green at a ~10%
 * wash rather than a saturated block, the naive reference is a hairline rule,
 * and the only direct label sits on the final forecast point — never one
 * number per marker.
 */
export function ForecastChart({
  history,
  forecasts,
  unit,
  title,
  subtitle,
}: {
  history: HistoryPoint[];
  forecasts: Forecast[];
  unit: string;
  title: string;
  subtitle?: string;
}) {
  const withValues = forecasts
    .filter((f) => f.p50 !== null)
    .sort((a, b) => a.horizon_weeks - b.horizon_weeks);

  const tail = history.slice(-52);
  const lastActual = tail.at(-1);

  const rows: Row[] = tail.map((h) => ({ week: h.week, actual: h.price }));

  if (lastActual && withValues.length) {
    // Anchor the cone on the last actual so the forecast reads as continuous.
    rows[rows.length - 1] = {
      ...rows[rows.length - 1],
      forecast: lastActual.price,
      band: [lastActual.price, lastActual.price],
      p10: lastActual.price,
      p90: lastActual.price,
    };
    for (const f of withValues) {
      rows.push({
        week: f.target_week_start,
        forecast: f.p50,
        band: [f.p10 as number, f.p90 as number],
        p10: f.p10,
        p90: f.p90,
      });
    }
  }

  const naive = lastActual?.price ?? null;
  const lastIndex = rows.length - 1;

  // Price is a level, not a magnitude growing from zero — anchoring the axis at
  // 0 flattens the whole series into a band at the top. Pad the observed range
  // instead. (Bars still grow from a baseline; this is a line chart.)
  const spread: number[] = rows.flatMap((r) =>
    [r.actual, r.p10, r.p90, r.forecast].filter((v): v is number => v != null),
  );
  const lo = Math.min(...spread);
  const hi = Math.max(...spread);
  const pad = Math.max((hi - lo) * 0.12, hi * 0.04, 1);
  const domain: [number, number] = spread.length
    ? [Math.max(0, lo - pad), hi + pad]
    : [0, 1];

  const series: SeriesKey[] = [
    { id: "actual", label: `Weekly ${forecasts[0]?.price_type ?? "wholesale"}`, color: "var(--series-1)" },
    { id: "forecast", label: "Forecast (P50)", color: "var(--series-1)", shape: "dashed" },
  ];
  if (naive !== null) {
    series.push({ id: "naive", label: "Last known price", color: "var(--series-2)", shape: "dashed" });
  }

  const table = {
    columns: ["Week", "Actual", "Forecast", "P10", "P90"],
    rows: rows
      .slice()
      .reverse()
      .slice(0, 60)
      .map((r) => [
        shortDate(r.week),
        r.actual != null ? kes(r.actual, 2) : "—",
        r.forecast != null ? kes(r.forecast, 2) : "—",
        r.p10 != null ? kes(r.p10, 2) : "—",
        r.p90 != null ? kes(r.p90, 2) : "—",
      ]),
  };

  return (
    <ChartFrame
      title={title}
      subtitle={subtitle}
      series={series}
      table={table}
      height={320}
      footnote={`Shaded band is the P10–P90 interval. The dotted rule is the naive baseline — quoting today's price unchanged. Prices in ${unit}.`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 12, right: 68, left: 4, bottom: 4 }}>
          <defs>
            <linearGradient id="forecastBand" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.16} />
              <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0.06} />
            </linearGradient>
          </defs>
          <CartesianGrid {...GRID} />
          <XAxis
            dataKey="week"
            tickFormatter={monthDate}
            minTickGap={44}
            tickMargin={10}
            {...AXIS}
          />
          <YAxis
            width={54}
            tickMargin={8}
            domain={domain}
            allowDataOverflow={false}
            tickFormatter={(v: number) => kes(v)}
            {...AXIS}
          />

          {naive !== null ? (
            <ReferenceLine
              y={naive}
              stroke="var(--series-2)"
              strokeWidth={1}
              strokeDasharray="4 4"
              ifOverflow="extendDomain"
            />
          ) : null}

          {/* Range area: a ~10% wash of the series hue, never a saturated block */}
          <Area
            dataKey="band"
            stroke="none"
            fill="url(#forecastBand)"
            isAnimationActive={false}
            activeDot={false}
            legendType="none"
            connectNulls
          />

          <Line
            dataKey="actual"
            stroke="var(--series-1)"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            dot={false}
            activeDot={{
              r: 4.5,
              fill: "var(--series-1)",
              stroke: "var(--surface-raised)",
              strokeWidth: 2,
            }}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            dataKey="forecast"
            stroke="var(--series-1)"
            strokeWidth={2}
            strokeDasharray="5 4"
            strokeLinecap="round"
            dot={{ r: 3.5, fill: "var(--series-1)", stroke: "var(--surface-raised)", strokeWidth: 2 }}
            activeDot={{
              r: 5,
              fill: "var(--series-1)",
              stroke: "var(--surface-raised)",
              strokeWidth: 2,
            }}
            isAnimationActive={false}
            connectNulls
          >
            {/* Direct-label the endpoint only. A number on every point is
                chaos and goes unread; the axis and tooltip carry the rest. */}
            <LabelList
              dataKey="forecast"
              content={(props) => {
                const { x, y, index, value } = props as {
                  x?: number;
                  y?: number;
                  index?: number;
                  value?: number;
                };
                if (index !== lastIndex || x == null || y == null || value == null) return null;
                return (
                  <text
                    x={x + 8}
                    y={y}
                    dy={4}
                    fontSize={11.5}
                    fontWeight={600}
                    fill="var(--text-primary)"
                  >
                    {kes(value, 0)}
                  </text>
                );
              }}
            />
          </Line>

          <Tooltip
            cursor={{ stroke: "var(--axis)", strokeWidth: 1 }}
            offset={14}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0]?.payload as Row | undefined;
              if (!row) return null;
              const out: { label: string; value: string; color?: string }[] = [];
              if (row.actual != null)
                out.push({ label: "Actual", value: kes(row.actual, 2), color: "var(--series-1)" });
              if (row.forecast != null && row.actual == null)
                out.push({ label: "Forecast", value: kes(row.forecast, 2), color: "var(--series-1)" });
              if (row.p10 != null && row.p90 != null && row.actual == null)
                out.push({ label: "Range", value: `${kes(row.p10, 2)} – ${kes(row.p90, 2)}` });
              if (!out.length) return null;
              return <TooltipCard title={shortDate(String(label))} rows={out} />;
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
