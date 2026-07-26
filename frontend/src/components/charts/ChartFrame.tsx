"use client";

import { useId, useState, type ReactNode } from "react";

import { cx } from "@/lib/format";

export interface SeriesKey {
  /** Stable identity — the color follows the entity, never its rank. */
  id: string;
  label: string;
  color: string;
  /** Line keys read as a rule, area/bar keys as a swatch. */
  shape?: "line" | "swatch" | "dashed";
}

export interface TableSpec {
  columns: string[];
  /** Pre-formatted strings; the table is the WCAG-clean twin of the chart. */
  rows: (string | number)[][];
}

/**
 * Card shell shared by every chart: title, legend, and a table-view twin.
 *
 * The table is not optional decoration — a sub-3:1 fill or a value the reader
 * can only reach by hovering has to be reachable another way, so every chart
 * ships one.
 */
export function ChartFrame({
  title,
  subtitle,
  series,
  table,
  children,
  height = 300,
  footnote,
  right,
}: {
  title: string;
  subtitle?: string;
  series?: SeriesKey[];
  table: TableSpec;
  children: ReactNode;
  height?: number;
  footnote?: string;
  right?: ReactNode;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const id = useId();

  return (
    <section className="hairline rounded-[var(--radius-card)] bg-[var(--surface-raised)] shadow-[var(--shadow-tile)]">
      <div className="flex flex-wrap items-start justify-between gap-3 px-6 pt-5">
        <div className="min-w-0">
          <h3 className="text-title text-[15px]">{title}</h3>
          {subtitle ? (
            <p className="mt-1 max-w-xl text-[13px] leading-relaxed text-[var(--text-secondary)]">
              {subtitle}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {right}
          <div
            role="tablist"
            aria-label={`${title} view`}
            className="hairline inline-flex rounded-full bg-[var(--surface-page)] p-0.5"
          >
            {(["chart", "table"] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={view === v}
                aria-controls={`${id}-${v}`}
                onClick={() => setView(v)}
                className={cx(
                  "rounded-full px-3 py-1 text-[12px] font-medium capitalize transition-colors",
                  view === v
                    ? "bg-[var(--surface-raised)] text-[var(--text-primary)] shadow-[var(--shadow-tile)]"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                )}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Legend is always present for 2+ series; identity is never color-alone
          because every key carries its text label. */}
      {series && series.length > 1 ? (
        <ul className="flex flex-wrap items-center gap-x-5 gap-y-2 px-6 pt-4">
          {series.map((s) => (
            <li key={s.id} className="flex items-center gap-2 text-[12.5px] text-[var(--text-secondary)]">
              {s.shape === "swatch" ? (
                <span
                  aria-hidden
                  className="size-2.5 rounded-[3px]"
                  style={{ background: s.color }}
                />
              ) : (
                <span
                  aria-hidden
                  className="h-0.5 w-4 rounded-full"
                  style={
                    s.shape === "dashed"
                      ? {
                          backgroundImage: `repeating-linear-gradient(90deg, ${s.color} 0 4px, transparent 4px 7px)`,
                        }
                      : { background: s.color }
                  }
                />
              )}
              {s.label}
            </li>
          ))}
        </ul>
      ) : null}

      {view === "chart" ? (
        <div id={`${id}-chart`} role="tabpanel" className="px-2 pt-3 pb-2" style={{ height }}>
          {children}
        </div>
      ) : (
        <div id={`${id}-table`} role="tabpanel" className="px-6 pt-4 pb-2">
          <div className="max-h-[320px] overflow-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="sticky top-0 bg-[var(--surface-raised)]">
                <tr className="text-[12px] tracking-wide text-[var(--text-muted)] uppercase">
                  {table.columns.map((c) => (
                    <th key={c} className="hairline-b py-2 pr-4 font-medium whitespace-nowrap">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr key={i} className="hairline-b last:border-0">
                    {row.map((cell, j) => (
                      <td
                        key={j}
                        className={cx(
                          "py-2 pr-4 whitespace-nowrap",
                          j === 0
                            ? "text-[var(--text-primary)]"
                            : "tnum text-[var(--text-secondary)]",
                        )}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {footnote ? (
        <p className="px-6 pt-2 pb-5 text-[12px] leading-relaxed text-[var(--text-muted)]">
          {footnote}
        </p>
      ) : (
        <div className="pb-4" />
      )}
    </section>
  );
}

/** Apple-ish tooltip surface. Values wear text tokens; the colored dot beside
 *  each row carries identity, never the text itself. */
export function TooltipCard({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: string; color?: string }[];
}) {
  return (
    <div className="hairline min-w-[168px] rounded-xl bg-[var(--surface-raised)] px-3 py-2.5 shadow-[var(--shadow-lift)]">
      <div className="text-[12px] font-medium text-[var(--text-muted)]">{title}</div>
      <ul className="mt-1.5 space-y-1">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center justify-between gap-4 text-[12.5px]">
            <span className="flex items-center gap-1.5 text-[var(--text-secondary)]">
              {r.color ? (
                <span aria-hidden className="size-2 rounded-full" style={{ background: r.color }} />
              ) : null}
              {r.label}
            </span>
            <span className="tnum font-medium text-[var(--text-primary)]">{r.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Axis/grid defaults shared by every chart: hairline solid gridlines one step
 *  off surface, recessive muted tick text, no axis lines competing with data. */
export const AXIS = {
  tick: { fill: "var(--text-muted)", fontSize: 11 },
  line: false as const,
  axisLine: false as const,
};

export const GRID = {
  stroke: "var(--gridline)",
  strokeWidth: 1,
  vertical: false,
};
