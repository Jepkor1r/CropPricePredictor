import { CoverageChart } from "@/components/charts/CoverageChart";
import { PageHeading } from "@/components/dashboard/Shell";
import { Card, CardHeader, Pill } from "@/components/ui/primitives";
import { getDashboard } from "@/lib/data";
import { compact, pct, shortDate } from "@/lib/format";

export const metadata = { title: "Coverage — PriceCast" };

export default async function CoveragePage() {
  const data = await getDashboard();
  const cappedFiles = data.files.filter((f) => f.hit_row_cap);

  return (
    <>
      <PageHeading
        title="Data coverage"
        description="What each KAMIS export actually contained, and how much of each crop's timeline carries a price. Exports cap at 3,000 rows and reflect whatever filter was active when they were pulled, so a truncated file is a fact worth showing rather than hiding."
      />

      <CoverageChart rows={data.coverage} />

      <div className="mt-4">
        <Card>
          <CardHeader
            title="Source files"
            subtitle="One row per export, as loaded. Overlapping files collapse onto the same key, so re-loading one changes nothing."
            right={
              cappedFiles.length ? (
                <Pill>
                  {cappedFiles.length} file{cappedFiles.length > 1 ? "s" : ""} hit the row cap
                </Pill>
              ) : null
            }
          />
          <div className="overflow-x-auto px-6 pb-6">
            <table className="w-full min-w-[860px] text-left text-[13px]">
              <thead>
                <tr className="text-[11.5px] tracking-wide text-[var(--text-muted)] uppercase">
                  {[
                    "File",
                    "Crop",
                    "Rows",
                    "After merge",
                    "Date range",
                    "Markets",
                    "Missing wholesale",
                    "Missing retail",
                  ].map((h) => (
                    <th key={h} className="hairline-b py-2.5 pr-4 font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.files.map((f) => (
                  <tr key={f.source_file} className="hairline-b last:border-0">
                    <td className="py-3 pr-4 font-medium whitespace-nowrap">
                      {f.source_file}
                      {f.hit_row_cap ? (
                        <span
                          className="ml-2 rounded-full px-1.5 py-0.5 text-[10.5px] font-semibold"
                          style={{
                            background: "color-mix(in srgb, var(--status-warning) 22%, transparent)",
                            color: "var(--text-primary)",
                          }}
                        >
                          capped
                        </span>
                      ) : null}
                    </td>
                    <td className="py-3 pr-4 whitespace-nowrap text-[var(--text-secondary)]">
                      {f.commodity}
                    </td>
                    <td className="tnum py-3 pr-4 whitespace-nowrap text-[var(--text-secondary)]">
                      {compact(f.n_rows_raw)}
                    </td>
                    <td className="tnum py-3 pr-4 whitespace-nowrap text-[var(--text-secondary)]">
                      {compact(f.n_rows_after_agg)}
                    </td>
                    <td className="py-3 pr-4 whitespace-nowrap text-[var(--text-secondary)]">
                      {shortDate(f.date_min)} — {shortDate(f.date_max)}
                    </td>
                    <td className="tnum py-3 pr-4 whitespace-nowrap text-[var(--text-secondary)]">
                      {f.n_markets}
                    </td>
                    <td className="tnum py-3 pr-4 whitespace-nowrap text-[var(--text-secondary)]">
                      {pct(f.pct_missing_wholesale, 1)}
                    </td>
                    <td className="tnum py-3 pr-4 whitespace-nowrap text-[var(--text-secondary)]">
                      {pct(f.pct_missing_retail, 1)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {data.coverage.map((c) => {
          const name =
            c.classification && c.classification !== "-"
              ? `${c.commodity} · ${c.classification}`
              : c.commodity;
          return (
            <Card key={name}>
              <div className="px-6 py-5">
                <h3 className="text-title text-[15px]">{name}</h3>
                <dl className="mt-4 space-y-2.5 text-[13px]">
                  {[
                    ["Weeks with a price", `${c.distinct_weeks} of ${c.span_weeks}`],
                    ["Markets reporting", String(c.n_markets)],
                    ["Largest gap", `${c.largest_gap_days} days`],
                    ["First observation", shortDate(c.date_min)],
                    ["Last observation", shortDate(c.date_max)],
                  ].map(([k, v]) => (
                    <div key={k} className="flex items-baseline justify-between gap-4">
                      <dt className="text-[var(--text-secondary)]">{k}</dt>
                      <dd className="tnum font-medium">{v}</dd>
                    </div>
                  ))}
                </dl>
                {c.largest_gap_days > 180 ? (
                  <p className="mt-4 text-[12.5px] leading-relaxed text-[var(--text-secondary)]">
                    A gap this long usually means two exports from different eras were merged
                    under one crop — the series either side of it are not continuous.
                  </p>
                ) : null}
              </div>
            </Card>
          );
        })}
      </div>
    </>
  );
}
