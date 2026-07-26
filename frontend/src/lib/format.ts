import type { Confidence, Tier } from "./types";

export const SERIES_SEP = "‖";

export function splitSeriesId(id: string) {
  const [commodity = "", classification = "", market = ""] = id.split(SERIES_SEP);
  return { commodity, classification, market };
}

/** Compact for display: 1,284 / 12.9K / 4.2M. Proportional figures, so no
 *  tabular-nums on these — that only belongs in aligned columns. */
export function compact(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 10_000) return `${(n / 1000).toFixed(abs >= 100_000 ? 0 : 1)}K`;
  return n.toLocaleString("en-KE");
}

export function kes(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-KE", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function monthDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit", timeZone: "UTC" });
}

export const TIER_LABEL: Record<Tier, string> = {
  model: "Model",
  seasonal_fallback: "Seasonal fallback",
  insufficient_data: "Insufficient data",
};

export const TIER_BLURB: Record<Tier, string> = {
  model: "26+ weeks of recent history — forecast from the gradient-boosted model.",
  seasonal_fallback: "8–25 weeks, or a crop the model can't beat — same-month average instead.",
  insufficient_data: "Too little history or the market stopped reporting. No forecast is offered.",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "Not scored",
};

/** Direction of travel between the last observed price and the forecast. */
export function trendOf(last: number | null, p50: number | null) {
  if (last === null || p50 === null || !last) return { key: "unknown" as const, label: "No trend", change: null };
  const change = (p50 - last) / last;
  if (change > 0.03) return { key: "rising" as const, label: "Rising", change };
  if (change < -0.03) return { key: "falling" as const, label: "Falling", change };
  return { key: "steady" as const, label: "Steady", change };
}

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}
