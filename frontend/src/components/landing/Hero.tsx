import Link from "next/link";

import { Sparkline } from "@/components/charts/Sparkline";
import { compact, kes, shortDate } from "@/lib/format";
import type { HistoryPoint, Kpis, SeriesRow } from "@/lib/types";

/** The one hero figure on the page, in the same sans as everything else. */
function HeroFigure({ kpis }: { kpis: Kpis }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="text-[clamp(3rem,7vw,4.5rem)] leading-none font-semibold tracking-[-0.045em]">
        {compact(kpis.observations)}
      </span>
      <span className="text-[15px] leading-snug text-[var(--text-secondary)]">
        market price records
        <br />
        across {kpis.markets} markets
      </span>
    </div>
  );
}

function ForecastPreview({
  featured,
  history,
}: {
  featured: SeriesRow | null;
  history: HistoryPoint[];
}) {
  if (!featured) return null;
  const rising = (featured.p50 ?? 0) >= (featured.last_price ?? 0);

  return (
    <div className="hairline w-full max-w-sm rounded-[26px] bg-[var(--surface-raised)] p-5 shadow-[var(--shadow-lift)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[12px] font-medium tracking-wide text-[var(--text-muted)] uppercase">
            {featured.market}, {featured.county}
          </div>
          <div className="mt-1 text-[17px] font-semibold tracking-[-0.02em]">
            {featured.commodity}
            {featured.classification !== "-" ? (
              <span className="text-[var(--text-secondary)]"> · {featured.classification}</span>
            ) : null}
          </div>
        </div>
        <Sparkline points={history} width={68} height={26} />
      </div>

      <div className="mt-5 flex items-end justify-between gap-4">
        <div>
          <div className="text-[12px] text-[var(--text-muted)]">Next week</div>
          <div className="mt-0.5 text-[34px] leading-none font-semibold tracking-[-0.035em]">
            {kes(featured.p50, 0)}
            <span className="ml-1 text-[15px] font-medium text-[var(--text-secondary)]">
              {featured.unit}
            </span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[12px] text-[var(--text-muted)]">Today</div>
          <div className="tnum mt-0.5 text-[15px] font-medium text-[var(--text-secondary)]">
            {kes(featured.last_price, 0)}
          </div>
        </div>
      </div>

      {/* Direction is information, not a verdict — a falling price is good for a
          buyer and bad for a seller, so this wears neutral ink rather than the
          reserved good/bad status colours. */}
      <div className="mt-4 flex items-center gap-2 text-[12.5px]">
        <span className="hairline inline-flex items-center gap-1.5 rounded-full px-2 py-1 font-medium text-[var(--text-secondary)]">
          <svg viewBox="0 0 12 12" className="size-3" aria-hidden fill="var(--series-1)">
            <path d={rising ? "M6 2.5 10 8H2z" : "M6 9.5 2 4h8z"} />
          </svg>
          {rising ? "Rising" : "Easing"}
        </span>
        <span className="tnum text-[var(--text-secondary)]">
          range {kes(featured.p10, 0)}–{kes(featured.p90, 0)}
        </span>
      </div>

      <div className="hairline-t mt-4 pt-3 text-[12px] leading-relaxed text-[var(--text-muted)]">
        Data through {shortDate(featured.as_of)}. Every forecast ships with the range it
        could land in, not just a single number.
      </div>
    </div>
  );
}

export function Hero({
  kpis,
  featured,
  history,
}: {
  kpis: Kpis;
  featured: SeriesRow | null;
  history: HistoryPoint[];
}) {
  return (
    <section className="grain relative isolate overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute top-[-18rem] left-1/2 size-[52rem] -translate-x-1/2 rounded-full bg-brand-300/25 blur-[110px] dark:bg-brand-700/25" />
      </div>

      <div className="mx-auto grid max-w-6xl items-center gap-14 px-6 pt-20 pb-16 lg:grid-cols-[1.05fr_0.95fr] lg:pt-24 lg:pb-20">
        <div className="reveal">
          <span className="hairline inline-flex items-center gap-2 rounded-full bg-[var(--surface-raised)] px-3 py-1.5 text-[12.5px] font-medium text-[var(--text-secondary)]">
            <span aria-hidden className="size-1.5 rounded-full bg-brand-500" />
            Built on Kenya&apos;s KAMIS market data
          </span>

          <h1 className="text-display mt-6 max-w-[13ch] text-[clamp(2.5rem,5.6vw,4rem)] text-balance">
            Know the price{" "}
            <span className="text-brand-600 dark:text-brand-400">
              before you leave the farm.
            </span>
          </h1>

          <p className="mt-6 max-w-lg text-[17px] leading-relaxed text-[var(--text-secondary)]">
            Smallholder farmers find out what their maize is worth when they arrive at
            market — with no time to compare, wait, or walk away. PriceCast forecasts
            next week&apos;s price for their crop, in their market, and sends it as a text
            message before they load the truck.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link
              href="/login"
              className="rounded-full bg-brand-600 px-6 py-3 text-[15px] font-semibold text-white shadow-[var(--shadow-tile)] transition-all hover:bg-brand-700 active:scale-[0.98]"
            >
              Open the dashboard
            </Link>
            <a
              href="#how"
              className="hairline rounded-full bg-[var(--surface-raised)] px-6 py-3 text-[15px] font-semibold transition-colors hover:bg-[var(--surface-page)]"
            >
              See how it works
            </a>
          </div>

          <div className="mt-11">
            <HeroFigure kpis={kpis} />
          </div>
          <p className="mt-3 max-w-md text-[13px] leading-relaxed text-[var(--text-muted)]">
            Ingested from Kenya&apos;s Agricultural Market Information System, cleaned and
            de-duplicated, covering {shortDate(kpis.dateMin)} to {shortDate(kpis.dateMax)}.
          </p>
        </div>

        <div className="reveal flex justify-center lg:justify-end" style={{ animationDelay: "120ms" }}>
          <ForecastPreview featured={featured} history={history} />
        </div>
      </div>
    </section>
  );
}
