"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS, ChartFrame, GRID, TooltipCard } from "./ChartFrame";
import { compact, shortDate } from "@/lib/format";
import type { CoverageRow } from "@/lib/types";

/**
 * Week coverage per crop.
 *
 * Nominal categories, one measure — so every bar wears the same slot-1 hue.
 * Colouring each bar by its own value would re-encode bar length as hue and
 * spend the identity channel on something length already shows. One series
 * means no legend box: the title says what is plotted.
 */
export function CoverageChart({ rows }: { rows: CoverageRow[] }) {
  const data = rows
    .map((r) => ({
      ...r,
      name:
        r.classification && r.classification !== "-"
          ? `${r.commodity} · ${r.classification}`
          : r.commodity,
    }))
    .sort((a, b) => b.week_coverage_pct - a.week_coverage_pct);

  const table = {
    columns: ["Series", "Coverage", "Weeks seen", "Span", "Markets", "Largest gap", "First", "Last"],
    rows: data.map((r) => [
      r.name,
      `${r.week_coverage_pct}%`,
      r.distinct_weeks,
      `${r.span_weeks}w`,
      r.n_markets,
      `${r.largest_gap_days}d`,
      shortDate(r.date_min),
      shortDate(r.date_max),
    ]),
  };

  return (
    <ChartFrame
      title="Reporting coverage by crop"
      subtitle="Share of weeks between a crop's first and last observation that actually carry a price. Gaps are visible here rather than smoothed away."
      table={table}
      height={Math.max(190, data.length * 46)}
      footnote="A high percentage over a short span still means thin history — read it alongside the span and market count in the table."
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 4, right: 56, left: 12, bottom: 4 }}
        >
          <CartesianGrid {...GRID} horizontal={false} vertical />
          <XAxis
            type="number"
            domain={[0, 100]}
            tickFormatter={(v: number) => `${v}%`}
            tickMargin={8}
            {...AXIS}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={148}
            tickMargin={8}
            {...AXIS}
            tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
          />
          <Bar dataKey="week_coverage_pct" maxBarSize={22} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((r) => (
              <Cell key={r.name} fill="var(--series-1)" />
            ))}
            {/* Value at the tip, outside the bar — never clipped by the mark. */}
            <LabelList
              dataKey="week_coverage_pct"
              position="right"
              offset={10}
              formatter={(v) => (v == null ? "" : `${v}%`)}
              style={{ fill: "var(--text-primary)", fontSize: 12, fontWeight: 600 }}
            />
          </Bar>
          <Tooltip
            cursor={{ fill: "color-mix(in srgb, var(--text-muted) 10%, transparent)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0]?.payload as (typeof data)[number];
              return (
                <TooltipCard
                  title={r.name}
                  rows={[
                    { label: "Coverage", value: `${r.week_coverage_pct}%`, color: "var(--series-1)" },
                    { label: "Weeks seen", value: `${r.distinct_weeks} of ${r.span_weeks}` },
                    { label: "Markets", value: compact(r.n_markets) },
                    { label: "Largest gap", value: `${r.largest_gap_days} days` },
                  ]}
                />
              );
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
