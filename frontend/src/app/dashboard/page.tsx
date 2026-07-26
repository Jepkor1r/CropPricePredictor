import Link from "next/link";

import { BacktestChart } from "@/components/charts/BacktestChart";
import { Sparkline } from "@/components/charts/Sparkline";
import { PageHeading } from "@/components/dashboard/Shell";
import {
  AnomalyBadge,
  Card,
  CardHeader,
  ConfidenceBadge,
  Empty,
  StatTile,
  TierBadge,
} from "@/components/ui/primitives";
import { getDashboard, getHistory } from "@/lib/data";
import {
  CONFIDENCE_LABEL,
  compact,
  kes,
  pct,
  shortDate,
  TIER_BLURB,
  TIER_LABEL,
  trendOf,
} from "@/lib/format";
import type { Tier } from "@/lib/types";

const TIER_ORDER: Tier[] = ["model", "seasonal_fallback", "insufficient_data"];

export default async function OverviewPage() {
  const [data, history] = await Promise.all([getDashboard(), getHistory()]);
  const { kpis } = data;

  const byTier = TIER_ORDER.map((tier) => ({
    tier,
    count: data.series.filter((s) => s.tier === tier).length,
  }));
  const total = data.series.length || 1;

  const highlights = data.series
    .filter((s) => s.tier === "model" && s.p50 !== null)
    .sort((a, b) => (b.n_weeks ?? 0) - (a.n_weeks ?? 0))
    .slice(0, 5);

  const anomalies = data.series.filter((s) => s.anomaly_flag === 1).slice(0, 4);

  const bestSkill = data.backtest
    .slice()
    .sort((a, b) => a.skill_vs_naive - b.skill_vs_naive)[0];

  return (
    <>
      <PageHeading
        title="Overview"
        description={`Every figure here is read from the pipeline's own tables — ${compact(kpis.observations)} price records covering ${kpis.markets} markets in ${kpis.counties} counties, from ${shortDate(kpis.dateMin)} to ${shortDate(kpis.dateMax)}.`}
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Forecastable series"
          value={`${kpis.forecastableSeries}`}
          hint={`of ${kpis.series} crop-and-market combinations`}
          accent
        />
        <StatTile
          label="Best backtested error"
          value={kpis.bestMape !== null ? pct(kpis.bestMape, 1) : "—"}
          hint={
            bestSkill
              ? `${bestSkill.commodity} at ${bestSkill.horizon}w · skill ${bestSkill.skill_vs_naive.toFixed(2)}`
              : "no backtest available"
          }
        />
        <StatTile
          label="Forecasts published"
          value={compact(kpis.forecastRows)}
          hint="1, 2 and 4 weeks ahead for every series"
        />
        <StatTile
          label="Markets flagged"
          value={`${kpis.anomalies}`}
          hint="price out of line with neighbouring markets"
        />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <BacktestChart rows={data.backtest} />

        <Card>
          <CardHeader
            title="How each series is served"
            subtitle="A series only reaches the model tier with 26+ weeks of recent history. Everything else is downgraded rather than guessed at."
          />
          <div className="space-y-4 px-6 pb-6">
            {byTier.map(({ tier, count }) => {
              const share = Math.round((count / total) * 100);
              return (
                <div key={tier}>
                  <div className="flex items-baseline justify-between gap-3">
                    <TierBadge tier={tier} label={TIER_LABEL[tier]} />
                    <span className="tnum text-[13px] font-medium">
                      {count}
                      <span className="ml-1.5 text-[var(--text-muted)]">{share}%</span>
                    </span>
                  </div>
                  {/* Meter: filled step + lighter track from the same ramp */}
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--gridline)]">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${share}%`,
                        background:
                          tier === "model"
                            ? "var(--ordinal-3)"
                            : tier === "seasonal_fallback"
                              ? "var(--ordinal-1)"
                              : "var(--text-muted)",
                      }}
                    />
                  </div>
                  <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--text-secondary)]">
                    {TIER_BLURB[tier]}
                  </p>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardHeader
            title="Best-covered markets"
            subtitle="The series with the longest run of recent weekly reports."
            right={
              <Link
                href="/dashboard/forecasts"
                className="text-[13px] font-medium text-brand-600 hover:underline dark:text-brand-400"
              >
                All forecasts →
              </Link>
            }
          />
          <ul>
            {highlights.map((s) => {
              const trend = trendOf(s.last_price, s.p50);
              return (
                <li
                  key={s.series_id}
                  className="hairline-t flex items-center gap-4 px-6 py-3.5 first:border-t-0"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[14px] font-medium">
                      {s.market}
                      <span className="text-[var(--text-secondary)]"> · {s.commodity}</span>
                    </div>
                    <div className="mt-0.5 text-[12.5px] text-[var(--text-muted)]">
                      {s.county} · {s.n_weeks} weekly reports
                    </div>
                  </div>
                  <Sparkline points={history[s.series_id] ?? []} />
                  <div className="w-[104px] text-right">
                    <div className="tnum text-[14px] font-semibold">{kes(s.p50, 0)}</div>
                    <div className="text-[12px] text-[var(--text-secondary)]">
                      {trend.label} · {s.unit}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="Price anomalies"
            subtitle="Markets sitting well above or below their neighbours in the same week. Detected arithmetically, not by the model."
          />
          {anomalies.length ? (
            <ul>
              {anomalies.map((s) => (
                <li key={s.series_id} className="hairline-t px-6 py-3.5 first:border-t-0">
                  <div className="text-[14px] font-medium">
                    {s.market}
                    <span className="text-[var(--text-secondary)]"> · {s.commodity}</span>
                  </div>
                  <div className="mt-2">
                    {s.anomaly_note ? <AnomalyBadge note={s.anomaly_note} /> : null}
                  </div>
                  <div className="mt-2 flex items-center gap-3 text-[12.5px] text-[var(--text-secondary)]">
                    <span className="tnum">Last {kes(s.last_price, 0)} {s.unit}</span>
                    <ConfidenceBadge
                      confidence={s.confidence}
                      label={CONFIDENCE_LABEL[s.confidence]}
                    />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <Empty
              title="No anomalies flagged"
              body="No market is currently more than 30% away from its county or national median."
            />
          )}
        </Card>
      </div>
    </>
  );
}
