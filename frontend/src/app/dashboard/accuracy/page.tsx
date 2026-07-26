import { BacktestChart } from "@/components/charts/BacktestChart";
import { PageHeading } from "@/components/dashboard/Shell";
import { Card, CardHeader, StatTile } from "@/components/ui/primitives";
import { getDashboard } from "@/lib/data";
import { pct } from "@/lib/format";

export const metadata = { title: "Accuracy — PriceCast" };

export default async function AccuracyPage() {
  const data = await getDashboard();
  const rows = data.backtest;

  const beats = rows.filter((r) => r.skill_vs_naive < 1);
  const loses = rows.filter((r) => r.skill_vs_naive >= 1);
  const bestRow = rows.slice().sort((a, b) => a.skill_vs_naive - b.skill_vs_naive)[0];
  const totalPoints = rows.reduce((sum, r) => sum + r.n, 0);

  return (
    <>
      <PageHeading
        title="Accuracy"
        description="Rolling-origin backtest. At each origin the model is retrained on everything up to that date and scored on what came next, so nothing in the evaluation was visible at training time. The bar to clear is the naive baseline a farmer already has: assume the price stays the same."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label="Crop-horizon pairs that beat naive"
          value={`${beats.length}/${rows.length}`}
          hint="skill below 1.00"
          accent
        />
        <StatTile
          label="Best skill score"
          value={bestRow ? bestRow.skill_vs_naive.toFixed(2) : "—"}
          hint={
            bestRow
              ? `${bestRow.commodity} at ${bestRow.horizon} week${bestRow.horizon > 1 ? "s" : ""} ahead`
              : undefined
          }
        />
        <StatTile
          label="Lowest error"
          value={data.kpis.bestMape !== null ? pct(data.kpis.bestMape, 1) : "—"}
          hint="mean absolute percentage error"
        />
        <StatTile
          label="Evaluated predictions"
          value={totalPoints.toLocaleString("en-KE")}
          hint="held-out points across all origins"
        />
      </div>

      <div className="mt-4">
        <BacktestChart rows={rows} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Where the model earns its keep"
            subtitle="Skill below 1.00 means less error than quoting today's price unchanged."
          />
          <ul className="px-6 pb-6">
            {beats
              .slice()
              .sort((a, b) => a.skill_vs_naive - b.skill_vs_naive)
              .map((r) => (
                <li
                  key={`${r.commodity}-${r.horizon}`}
                  className="hairline-t flex items-center justify-between gap-4 py-3 first:border-t-0"
                >
                  <div>
                    <div className="text-[14px] font-medium">{r.commodity}</div>
                    <div className="text-[12.5px] text-[var(--text-secondary)]">
                      {r.horizon} week{r.horizon > 1 ? "s" : ""} ahead · {r.n} points
                    </div>
                  </div>
                  <div className="text-right">
                    <div
                      className="tnum text-[15px] font-semibold"
                      style={{ color: "var(--success-text)" }}
                    >
                      {r.skill_vs_naive.toFixed(2)}
                    </div>
                    <div className="tnum text-[12px] text-[var(--text-secondary)]">
                      {pct(r.mape_model, 1)} vs {pct(r.mape_naive, 1)}
                    </div>
                  </div>
                </li>
              ))}
            {!beats.length ? (
              <li className="py-6 text-center text-[13.5px] text-[var(--text-secondary)]">
                No crop-horizon pair currently beats the baseline.
              </li>
            ) : null}
          </ul>
        </Card>

        <Card>
          <CardHeader
            title="Where it doesn't"
            subtitle="These fall back to a baseline and are labelled low confidence. Weekly prices are sticky — a large share of weeks repeat the previous price exactly — which makes short horizons genuinely hard to beat."
          />
          <ul className="px-6 pb-6">
            {loses
              .slice()
              .sort((a, b) => b.skill_vs_naive - a.skill_vs_naive)
              .map((r) => (
                <li
                  key={`${r.commodity}-${r.horizon}`}
                  className="hairline-t flex items-center justify-between gap-4 py-3 first:border-t-0"
                >
                  <div>
                    <div className="text-[14px] font-medium">{r.commodity}</div>
                    <div className="text-[12.5px] text-[var(--text-secondary)]">
                      {r.horizon} week{r.horizon > 1 ? "s" : ""} ahead · {r.n} points
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="tnum text-[15px] font-semibold text-[var(--text-primary)]">
                      {r.skill_vs_naive.toFixed(2)}
                    </div>
                    <div className="tnum text-[12px] text-[var(--text-secondary)]">
                      {pct(r.mape_model, 1)} vs {pct(r.mape_naive, 1)}
                    </div>
                  </div>
                </li>
              ))}
            {!loses.length ? (
              <li className="py-6 text-center text-[13.5px] text-[var(--text-secondary)]">
                Every crop-horizon pair beats the baseline.
              </li>
            ) : null}
          </ul>
        </Card>
      </div>
    </>
  );
}
