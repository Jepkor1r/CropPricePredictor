import Link from "next/link";

import { compact, kes, pct } from "@/lib/format";
import type { BacktestRow, Kpis } from "@/lib/types";

export function StatStrip({ kpis }: { kpis: Kpis }) {
  // The hero figure already carries the record count and market count, so this
  // strip complements it rather than restating it.
  const items = [
    { value: String(kpis.counties), label: "Counties reached" },
    { value: String(kpis.commodities), label: "Crops tracked" },
    { value: String(kpis.series), label: "Crop-market series" },
    { value: compact(kpis.forecastRows), label: "Forecasts published" },
    {
      value: kpis.bestMape !== null ? pct(kpis.bestMape, 1) : "—",
      label: "Best backtested error",
    },
  ];
  return (
    <section className="hairline-t hairline-b bg-[var(--surface-raised)]">
      <div className="mx-auto grid max-w-6xl grid-cols-2 gap-y-8 px-6 py-10 sm:grid-cols-3 lg:grid-cols-5">
        {items.map((i) => (
          <div key={i.label}>
            <div className="text-[26px] leading-none font-semibold tracking-[-0.03em]">
              {i.value}
            </div>
            <div className="mt-1.5 text-[12.5px] text-[var(--text-secondary)]">{i.label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SectionHeading({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <div className="text-[12.5px] font-semibold tracking-[0.08em] text-brand-600 uppercase dark:text-brand-400">
        {eyebrow}
      </div>
      <h2 className="text-title mt-3 text-[clamp(1.9rem,4vw,2.75rem)]">{title}</h2>
      <p className="mt-4 text-[16.5px] leading-relaxed text-[var(--text-secondary)]">{body}</p>
    </div>
  );
}

const PIPELINE = [
  {
    step: "01",
    title: "Ingest",
    body: "KAMIS spreadsheet exports land as-is. Prices arrive as strings like “38.89/Kg”, wholesale and retail split across separate rows, and “-” meaning not reported. All of it is parsed, merged and de-duplicated on the way in.",
  },
  {
    step: "02",
    title: "Reconcile",
    body: "Overlapping exports collapse onto one key per market per day, so re-loading the same file changes nothing. Every file's real date range and market count is reported, so gaps stay visible instead of being assumed away.",
  },
  {
    step: "03",
    title: "Forecast",
    body: "A gradient-boosted model trained across every market predicts 1, 2 and 4 weeks ahead — on a scale-invariant target, so a 2005 tomato price and a 2026 maize price can inform the same model.",
  },
  {
    step: "04",
    title: "Explain",
    body: "Claude turns the numbers into one plain-language sentence a farmer can act on, in English or Kiswahili, short enough to arrive as a single SMS.",
  },
];

export function Pipeline() {
  return (
    <section id="how" className="mx-auto max-w-6xl px-6 py-24">
      <SectionHeading
        eyebrow="How it works"
        title="From a messy spreadsheet to a sentence that fits in a text message."
        body="Four stages, each one auditable. Nothing is smoothed over to make the demo look better than the data is."
      />
      <ol className="mt-14 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {PIPELINE.map((p) => (
          <li
            key={p.step}
            className="hairline rounded-[var(--radius-card)] bg-[var(--surface-raised)] p-6 shadow-[var(--shadow-tile)]"
          >
            <div className="grid size-9 place-items-center rounded-full bg-brand-50 text-[13px] font-semibold text-brand-700 dark:bg-brand-900/50 dark:text-brand-300">
              {p.step}
            </div>
            <h3 className="text-title mt-4 text-[17px]">{p.title}</h3>
            <p className="mt-2.5 text-[14px] leading-relaxed text-[var(--text-secondary)]">
              {p.body}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}

export function HonestySection({ backtest }: { backtest: BacktestRow[] }) {
  const best = backtest.filter((b) => b.skill_vs_naive < 1).sort((a, b) => a.skill_vs_naive - b.skill_vs_naive)[0];
  const worst = backtest.slice().sort((a, b) => b.skill_vs_naive - a.skill_vs_naive)[0];

  return (
    <section id="accuracy" className="hairline-t bg-[var(--surface-raised)]">
      <div className="mx-auto max-w-6xl px-6 py-24">
        <SectionHeading
          eyebrow="Honest by construction"
          title="A forecast that can't beat “today's price” says so."
          body="Every crop is scored by rolling-origin backtest against the naive baseline a farmer already has: assume the price stays the same. Where the model loses, the dashboard shows it losing."
        />

        <div className="mt-14 grid gap-4 lg:grid-cols-3">
          <div className="hairline rounded-[var(--radius-card)] bg-[var(--surface-page)] p-7">
            <div className="text-[12.5px] font-medium tracking-wide text-[var(--text-muted)] uppercase">
              Where it wins
            </div>
            {best ? (
              <>
                <div className="mt-3 text-[38px] leading-none font-semibold tracking-[-0.035em] text-brand-600 dark:text-brand-400">
                  {Math.round((1 - best.skill_vs_naive) * 100)}%
                </div>
                <p className="mt-3 text-[14px] leading-relaxed text-[var(--text-secondary)]">
                  less error than the naive baseline for <strong>{best.commodity}</strong> at{" "}
                  {best.horizon} week{best.horizon > 1 ? "s" : ""} ahead — {pct(best.mape_model, 1)}{" "}
                  versus {pct(best.mape_naive, 1)}.
                </p>
              </>
            ) : (
              <p className="mt-3 text-[14px] text-[var(--text-secondary)]">
                No crop currently beats the baseline.
              </p>
            )}
          </div>

          <div className="hairline rounded-[var(--radius-card)] bg-[var(--surface-page)] p-7">
            <div className="text-[12.5px] font-medium tracking-wide text-[var(--text-muted)] uppercase">
              Where it doesn&apos;t
            </div>
            {worst ? (
              <>
                <div className="mt-3 text-[38px] leading-none font-semibold tracking-[-0.035em]">
                  {worst.skill_vs_naive.toFixed(2)}
                </div>
                <p className="mt-3 text-[14px] leading-relaxed text-[var(--text-secondary)]">
                  skill score for <strong>{worst.commodity}</strong> at {worst.horizon} week
                  {worst.horizon > 1 ? "s" : ""} — above 1.00, so the model is worse than
                  quoting today&apos;s price. Those forecasts fall back to a baseline and are
                  labelled low confidence.
                </p>
              </>
            ) : null}
          </div>

          <div className="hairline rounded-[var(--radius-card)] bg-[var(--surface-page)] p-7">
            <div className="text-[12.5px] font-medium tracking-wide text-[var(--text-muted)] uppercase">
              Where there isn&apos;t enough data
            </div>
            <div className="mt-3 text-[38px] leading-none font-semibold tracking-[-0.035em]">
              No guess
            </div>
            <p className="mt-3 text-[14px] leading-relaxed text-[var(--text-secondary)]">
              A market with under eight weeks of history, or one that stopped reporting,
              gets no forecast at all. The message names the nearest covered market
              instead of inventing a number.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

export function DeliverySection({ sms }: { sms: string[] }) {
  return (
    <section id="delivery" className="mx-auto max-w-6xl px-6 py-24">
      <div className="grid items-center gap-14 lg:grid-cols-2">
        <div>
          <div className="text-[12.5px] font-semibold tracking-[0.08em] text-brand-600 uppercase dark:text-brand-400">
            Built for the phone farmers own
          </div>
          <h2 className="text-title mt-3 text-[clamp(1.9rem,4vw,2.75rem)]">
            160 characters, no app, no data bundle.
          </h2>
          <p className="mt-5 text-[16.5px] leading-relaxed text-[var(--text-secondary)]">
            The dashboard is for cooperatives and extension officers. The farmer gets a
            text. Claude turns each forecast into one sentence with the numbers rounded,
            the direction stated plainly, and a warning when the local price is out of
            line with neighbouring markets.
          </p>
          <ul className="mt-8 space-y-3.5">
            {[
              "English or Kiswahili, chosen per subscriber",
              "Validated before sending — length and figures are checked, with a deterministic fallback if the model drifts",
              "USSD menu planned for on-demand lookups from any feature phone",
            ].map((t) => (
              <li key={t} className="flex gap-3 text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
                <svg viewBox="0 0 20 20" className="mt-0.5 size-4 shrink-0" aria-hidden>
                  <circle cx="10" cy="10" r="9" fill="var(--series-1)" opacity="0.14" />
                  <path
                    d="m6.5 10.5 2.2 2.2 4.8-5"
                    fill="none"
                    stroke="var(--success-text)"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                {t}
              </li>
            ))}
          </ul>
        </div>

        <div className="flex justify-center">
          <PhoneMock messages={sms} />
        </div>
      </div>
    </section>
  );
}

export function PhoneMock({ messages }: { messages: string[] }) {
  return (
    <div className="hairline w-full max-w-[320px] rounded-[38px] bg-[var(--surface-raised)] p-3 shadow-[var(--shadow-lift)]">
      <div className="rounded-[28px] bg-[var(--surface-page)] px-4 pt-5 pb-6">
        <div className="mx-auto mb-5 h-1.5 w-16 rounded-full bg-[var(--axis)]" />
        <div className="text-center text-[12px] font-medium text-[var(--text-muted)]">
          PriceCast · SMS
        </div>
        <div className="mt-4 space-y-2.5">
          {messages.slice(0, 3).map((m, i) => (
            <div
              key={i}
              className="rounded-2xl rounded-bl-md bg-brand-600 px-3.5 py-2.5 text-[13px] leading-relaxed text-white"
            >
              {m}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function DataSection({ kpis }: { kpis: Kpis }) {
  return (
    <section id="data" className="hairline-t bg-[var(--surface-raised)]">
      <div className="mx-auto max-w-6xl px-6 py-24">
        <SectionHeading
          eyebrow="The data underneath"
          title="Real exports, real gaps, reported honestly."
          body="KAMIS exports cap at 3,000 rows and reflect whatever filter was active when they were pulled. The dashboard surfaces exactly what each file contained so nobody mistakes a gap for a stable price."
        />
        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            { k: kes(kpis.observations), v: "Observations after de-duplication" },
            { k: `${kpis.series}`, v: "Crop-and-market series tracked" },
            { k: `${kpis.forecastableSeries}`, v: "Series with enough data to forecast" },
            { k: `${kpis.anomalies}`, v: "Markets flagged as out of line" },
          ].map((s) => (
            <div key={s.v} className="hairline rounded-[var(--radius-card)] bg-[var(--surface-page)] p-6">
              <div className="text-[30px] leading-none font-semibold tracking-[-0.03em]">{s.k}</div>
              <div className="mt-2 text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
                {s.v}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-24">
      <div className="relative isolate overflow-hidden rounded-[32px] bg-brand-700 px-8 py-16 text-center sm:px-16">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 size-[34rem] -translate-x-1/2 rounded-full bg-brand-400/25 blur-[90px]"
        />
        <h2 className="text-title relative text-[clamp(1.9rem,4vw,2.6rem)] text-white">
          Explore the whole pipeline.
        </h2>
        <p className="relative mx-auto mt-4 max-w-xl text-[16.5px] leading-relaxed text-brand-100">
          Coverage, accuracy, forecasts and the exact messages that would reach farmers —
          all reading from the same database the model writes to.
        </p>
        <Link
          href="/login"
          className="relative mt-9 inline-flex rounded-full bg-white px-7 py-3.5 text-[15px] font-semibold text-brand-800 transition-transform active:scale-[0.98]"
        >
          Open the dashboard
        </Link>
      </div>
    </section>
  );
}

export function Footer({ generatedAt }: { generatedAt: string }) {
  return (
    <footer className="hairline-t">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-10 text-[13px] text-[var(--text-muted)] sm:flex-row sm:items-center sm:justify-between">
        <p>
          PriceCast — a demonstration build on Kenya&apos;s Agricultural Market Information
          System data.
        </p>
        <p className="tnum">Data snapshot {generatedAt.slice(0, 10)}</p>
      </div>
    </footer>
  );
}
