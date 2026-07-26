"use client";

import { useMemo, useState } from "react";

import { ForecastChart } from "@/components/charts/ForecastChart";
import { Sparkline } from "@/components/charts/Sparkline";
import {
  AnomalyBadge,
  Card,
  CardHeader,
  ConfidenceBadge,
  Empty,
  Pill,
  TierBadge,
} from "@/components/ui/primitives";
import {
  CONFIDENCE_LABEL,
  cx,
  kes,
  shortDate,
  TIER_BLURB,
  TIER_LABEL,
  trendOf,
} from "@/lib/format";
import type { Forecast, History, SeriesRow, Tier } from "@/lib/types";

const TIER_FILTERS: { key: Tier | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "model", label: "Model" },
  { key: "seasonal_fallback", label: "Fallback" },
  { key: "insufficient_data", label: "No forecast" },
];

/**
 * Filter row sits above everything it scopes, and every panel below re-renders
 * against the same slice — never a filter inside a chart card.
 */
export function ForecastExplorer({
  series,
  forecasts,
  history,
  commodities,
}: {
  series: SeriesRow[];
  forecasts: Forecast[];
  history: History;
  commodities: string[];
}) {
  const [commodity, setCommodity] = useState<string>("all");
  const [tier, setTier] = useState<Tier | "all">("model");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return series.filter((s) => {
      if (commodity !== "all" && s.commodity !== commodity) return false;
      if (tier !== "all" && s.tier !== tier) return false;
      if (q && !`${s.market} ${s.county} ${s.commodity}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [series, commodity, tier, query]);

  const selected = useMemo(() => {
    const fromList = filtered.find((s) => s.series_id === selectedId);
    return fromList ?? filtered[0] ?? null;
  }, [filtered, selectedId]);

  const selectedForecasts = useMemo(
    () => (selected ? forecasts.filter((f) => f.series_id === selected.series_id) : []),
    [forecasts, selected],
  );

  return (
    <>
      {/* One filter row above everything it scopes */}
      <div className="hairline mb-4 flex flex-wrap items-center gap-2.5 rounded-[var(--radius-tile)] bg-[var(--surface-raised)] px-4 py-3">
        <label className="relative flex-1 basis-56">
          <span className="sr-only">Search market, county or crop</span>
          <svg
            viewBox="0 0 20 20"
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-[var(--text-muted)]"
            fill="none"
          >
            <circle cx="9" cy="9" r="5.5" stroke="currentColor" strokeWidth="1.7" />
            <path d="m13.5 13.5 3 3" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
          </svg>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search market, county or crop"
            className="hairline w-full rounded-full bg-[var(--surface-page)] py-2 pr-3 pl-9 text-[13.5px]"
          />
        </label>

        <select
          value={commodity}
          onChange={(e) => setCommodity(e.target.value)}
          aria-label="Filter by crop"
          className="hairline rounded-full bg-[var(--surface-page)] px-3.5 py-2 text-[13.5px]"
        >
          <option value="all">All crops</option>
          {commodities.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <div
          role="group"
          aria-label="Filter by tier"
          className="hairline inline-flex rounded-full bg-[var(--surface-page)] p-0.5"
        >
          {TIER_FILTERS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTier(t.key)}
              aria-pressed={tier === t.key}
              className={cx(
                "rounded-full px-3 py-1.5 text-[12.5px] font-medium transition-colors",
                tier === t.key
                  ? "bg-[var(--surface-raised)] text-[var(--text-primary)] shadow-[var(--shadow-tile)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <span className="tnum ml-auto text-[12.5px] text-[var(--text-muted)]">
          {filtered.length} series
        </span>
      </div>

      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        {/* Series list */}
        <Card className="max-h-[720px] overflow-hidden">
          <CardHeader title="Series" subtitle="Ordered by forecast quality, then by crop." />
          <div className="max-h-[608px] overflow-y-auto">
            {filtered.length ? (
              <ul>
                {filtered.slice(0, 250).map((s) => {
                  const active = selected?.series_id === s.series_id;
                  return (
                    <li key={s.series_id}>
                      <button
                        onClick={() => setSelectedId(s.series_id)}
                        aria-current={active ? "true" : undefined}
                        className={cx(
                          "hairline-t flex w-full items-center gap-3 px-6 py-3 text-left transition-colors",
                          active ? "bg-brand-50 dark:bg-brand-900/25" : "hover:bg-[var(--surface-page)]",
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[13.5px] font-medium">{s.market}</div>
                          <div className="mt-0.5 truncate text-[12px] text-[var(--text-muted)]">
                            {s.commodity}
                            {s.classification !== "-" ? ` · ${s.classification}` : ""} · {s.county}
                          </div>
                        </div>
                        <Sparkline points={history[s.series_id] ?? []} width={56} height={20} />
                        <div className="w-[72px] text-right">
                          <div className="tnum text-[13px] font-semibold">
                            {s.p50 !== null ? kes(s.p50, 0) : "—"}
                          </div>
                          <div className="text-[11px] text-[var(--text-muted)]">
                            {s.tier === "insufficient_data" ? "no data" : TIER_LABEL[s.tier]}
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <Empty
                title="Nothing matches those filters"
                body="Try a different crop, or widen the tier filter to include fallback and no-forecast series."
              />
            )}
          </div>
        </Card>

        {/* Detail */}
        <div className="space-y-4">
          {selected ? (
            <SeriesDetail
              series={selected}
              forecasts={selectedForecasts}
              history={history[selected.series_id] ?? []}
            />
          ) : (
            <Card>
              <Empty
                title="No series selected"
                body="Pick a market from the list to see its history, forecast cone and confidence."
              />
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function SeriesDetail({
  series,
  forecasts,
  history,
}: {
  series: SeriesRow;
  forecasts: Forecast[];
  history: import("@/lib/types").HistoryPoint[];
}) {
  const ordered = forecasts.slice().sort((a, b) => a.horizon_weeks - b.horizon_weeks);
  const usable = ordered.filter((f) => f.p50 !== null);
  const staleWeeks =
    series.last_price_date && series.as_of
      ? Math.round(
          (Date.parse(`${series.as_of}T00:00:00Z`) -
            Date.parse(`${series.last_price_date}T00:00:00Z`)) /
            (7 * 864e5),
        )
      : 0;

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4 px-6 pt-5 pb-4">
          <div>
            <h2 className="text-title text-[19px]">
              {series.market}
              <span className="text-[var(--text-secondary)]"> · {series.commodity}</span>
            </h2>
            <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {series.county}
              {series.classification !== "-" ? ` · ${series.classification}` : ""} ·{" "}
              {series.n_weeks ?? 0} weekly reports · data through {shortDate(series.as_of)}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <TierBadge tier={series.tier} label={TIER_LABEL[series.tier]} />
            {series.confidence !== "none" ? (
              <ConfidenceBadge
                confidence={series.confidence}
                label={CONFIDENCE_LABEL[series.confidence]}
              />
            ) : null}
          </div>
        </div>

        {series.anomaly_note ? (
          <div className="px-6 pb-4">
            <AnomalyBadge note={series.anomaly_note} />
          </div>
        ) : null}

        {usable.length ? (
          <div className="grid gap-3 px-6 pb-6 sm:grid-cols-4">
            <div className="hairline rounded-[var(--radius-tile)] bg-[var(--surface-page)] px-4 py-3">
              <div className="text-[11.5px] tracking-wide text-[var(--text-muted)] uppercase">
                Last {series.price_type}
              </div>
              <div className="mt-1.5 text-[22px] leading-none font-semibold tracking-[-0.03em]">
                {kes(series.last_price, 0)}
              </div>
              <div className="mt-1.5 text-[11.5px] text-[var(--text-secondary)]">
                {shortDate(series.last_price_date)}
              </div>
            </div>
            {usable.map((f) => {
              const trend = trendOf(series.last_price, f.p50);
              return (
                <div
                  key={f.horizon_weeks}
                  className="hairline rounded-[var(--radius-tile)] bg-[var(--surface-page)] px-4 py-3"
                >
                  <div className="text-[11.5px] tracking-wide text-[var(--text-muted)] uppercase">
                    {f.horizon_weeks === 1 ? "Next week" : `In ${f.horizon_weeks} weeks`}
                  </div>
                  <div className="mt-1.5 text-[22px] leading-none font-semibold tracking-[-0.03em]">
                    {kes(f.p50, 0)}
                  </div>
                  <div className="tnum mt-1.5 text-[11.5px] text-[var(--text-secondary)]">
                    {kes(f.p10, 0)}–{kes(f.p90, 0)} · {trend.label}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="px-6 pb-6">
            <div className="hairline rounded-[var(--radius-tile)] bg-[var(--surface-page)] px-5 py-4">
              <p className="text-[14px] font-medium">No forecast is offered for this market.</p>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--text-secondary)]">
                {staleWeeks > 8
                  ? `The last report here was ${shortDate(series.last_price_date)} — ${staleWeeks} weeks before this crop's most recent data. Too stale to forecast from.`
                  : `Only ${series.n_weeks ?? 0} weeks of history, below the eight-week minimum.`}{" "}
                {TIER_BLURB.insufficient_data}
              </p>
            </div>
          </div>
        )}
      </Card>

      {history.length > 1 ? (
        <ForecastChart
          history={history}
          forecasts={ordered}
          unit={series.unit}
          title="Weekly price and forecast cone"
          subtitle={`${series.commodity} at ${series.market}. The cone widens with the horizon because the model is less sure further out.`}
        />
      ) : null}

      {series.sms_text ? (
        <Card>
          <CardHeader
            title="The message a farmer receives"
            subtitle="Generated by Claude from the numbers above, validated for length and figures before it would be sent."
          />
          <div className="px-6 pb-6">
            <div className="rounded-2xl rounded-bl-md bg-brand-600 px-4 py-3 text-[13.5px] leading-relaxed text-white">
              {series.sms_text}
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <Pill>{series.sms_text.length} characters</Pill>
              <Pill>Single SMS</Pill>
            </div>
          </div>
        </Card>
      ) : null}
    </>
  );
}
