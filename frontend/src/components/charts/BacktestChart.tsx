"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS, ChartFrame, GRID, TooltipCard, type SeriesKey } from "./ChartFrame";
import { pct } from "@/lib/format";
import type { BacktestRow } from "@/lib/types";

const SERIES: SeriesKey[] = [
  { id: "mape_model", label: "Model", color: "var(--series-1)", shape: "swatch" },
  { id: "mape_naive", label: "Last known price", color: "var(--series-2)", shape: "swatch" },
  { id: "mape_seasonal", label: "Seasonal average", color: "var(--series-3)", shape: "swatch" },
];

/**
 * Backtest error by crop and horizon, as small multiples.
 *
 * One panel per crop rather than twelve bars on a single axis: with three
 * methods across three horizons a combined chart buries the comparison the
 * reader actually wants, which is model-vs-baseline within a crop. Lower is
 * better, and every panel shares one y-scale so panels are comparable.
 */
export function BacktestChart({ rows }: { rows: BacktestRow[] }) {
  const commodities = [...new Set(rows.map((r) => r.commodity))].sort();
  const max = Math.max(
    ...rows.flatMap((r) => [r.mape_model, r.mape_naive, r.mape_seasonal]),
    10,
  );
  const domainMax = Math.ceil(max / 10) * 10;

  const table = {
    columns: ["Crop", "Horizon", "Model", "Last price", "Seasonal", "Skill vs naive"],
    rows: rows.map((r) => [
      r.commodity,
      `${r.horizon}w`,
      pct(r.mape_model, 1),
      pct(r.mape_naive, 1),
      pct(r.mape_seasonal, 1),
      r.skill_vs_naive.toFixed(2),
    ]),
  };

  return (
    <ChartFrame
      title="Backtested error by crop and horizon"
      subtitle="Rolling-origin evaluation. Bars are mean absolute percentage error — shorter is better. The model earns its keep only where its bar is shorter than the last-known-price bar."
      series={SERIES}
      table={table}
      height={commodities.length > 2 ? 340 : 190}
      footnote="Skill = model error ÷ naive error; below 1.00 beats quoting today's price unchanged."
    >
      <div className="grid h-full grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {commodities.map((commodity) => {
          const data = rows
            .filter((r) => r.commodity === commodity)
            .sort((a, b) => a.horizon - b.horizon)
            .map((r) => ({ ...r, horizonLabel: `${r.horizon}w` }));
          return (
            <div key={commodity} className="flex min-h-0 flex-col">
              <div className="px-4 text-[12.5px] font-medium text-[var(--text-secondary)]">
                {commodity}
              </div>
              <div className="min-h-0 flex-1">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data} margin={{ top: 6, right: 8, left: 0, bottom: 0 }} barGap={2}>
                    <CartesianGrid {...GRID} />
                    <XAxis dataKey="horizonLabel" tickMargin={6} {...AXIS} />
                    <YAxis
                      width={38}
                      domain={[0, domainMax]}
                      tickFormatter={(v: number) => `${v}%`}
                      {...AXIS}
                    />
                    {SERIES.map((s) => (
                      <Bar
                        key={s.id}
                        dataKey={s.id}
                        fill={s.color}
                        maxBarSize={22}
                        radius={[4, 4, 0, 0]}
                        isAnimationActive={false}
                      />
                    ))}
                    <Tooltip
                      cursor={{ fill: "color-mix(in srgb, var(--text-muted) 10%, transparent)" }}
                      content={({ active, payload, label }) => {
                        if (!active || !payload?.length) return null;
                        const row = payload[0]?.payload as BacktestRow;
                        return (
                          <TooltipCard
                            title={`${commodity} · ${label} ahead`}
                            rows={[
                              ...SERIES.map((s) => ({
                                label: s.label,
                                value: pct(row[s.id as keyof BacktestRow] as number, 1),
                                color: s.color,
                              })),
                              { label: "Skill vs naive", value: row.skill_vs_naive.toFixed(2) },
                            ]}
                          />
                        );
                      }}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        })}
      </div>
    </ChartFrame>
  );
}
