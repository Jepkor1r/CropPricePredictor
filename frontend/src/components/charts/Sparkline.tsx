"use client";

import type { HistoryPoint } from "@/lib/types";

/**
 * Twelve-ish point trend line for stat tiles and list rows.
 *
 * Deliberately not a Recharts instance: hundreds of these render in the series
 * list, and a bare SVG path keeps that cheap. No axes, no tooltip — the value
 * beside it carries the number.
 */
export function Sparkline({
  points,
  width = 76,
  height = 24,
  color = "var(--series-1)",
}: {
  points: HistoryPoint[];
  width?: number;
  height?: number;
  color?: string;
}) {
  const values = points.slice(-16).map((p) => p.price);
  if (values.length < 2) {
    return <div style={{ width, height }} aria-hidden />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 2;
  const stepX = (width - pad * 2) / (values.length - 1);

  const coords = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (height - pad * 2) * (1 - (v - min) / span);
    return [x, y] as const;
  });

  const d = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const [lastX, lastY] = coords[coords.length - 1];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden
      className="overflow-visible"
    >
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      {/* 2px surface ring keeps the end dot legible where it crosses the line */}
      <circle cx={lastX} cy={lastY} r={2.75} fill={color} stroke="var(--surface-raised)" strokeWidth={2} />
    </svg>
  );
}
