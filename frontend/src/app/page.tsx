import { Hero } from "@/components/landing/Hero";
import { Nav } from "@/components/landing/Nav";
import {
  DataSection,
  DeliverySection,
  FinalCta,
  Footer,
  HonestySection,
  Pipeline,
  StatStrip,
} from "@/components/landing/Sections";
import { getDashboard, getHistory } from "@/lib/data";

export default async function LandingPage() {
  const [data, history] = await Promise.all([getDashboard(), getHistory()]);

  // Lead with a series that actually has a model-tier forecast and a decent run
  // of history, so the hero shows the product working rather than a stub.
  const featured =
    data.series
      .filter((s) => s.tier === "model" && s.p50 !== null)
      .sort((a, b) => (b.n_weeks ?? 0) - (a.n_weeks ?? 0))[0] ?? null;

  const sms = data.forecasts
    .filter((f) => f.sms_text)
    .map((f) => f.sms_text as string)
    .slice(0, 3);

  return (
    <>
      <Nav />
      <main className="flex-1">
        <Hero
          kpis={data.kpis}
          featured={featured}
          history={featured ? (history[featured.series_id] ?? []) : []}
        />
        <StatStrip kpis={data.kpis} />
        <Pipeline />
        <HonestySection backtest={data.backtest} />
        <DeliverySection
          sms={
            sms.length
              ? sms
              : [
                  "Ahero Dry Maize (wholesale): now 55 KES/kg, expected ~54 KES/kg next week. Trend: steady.",
                ]
          }
        />
        <DataSection kpis={data.kpis} />
        <FinalCta />
      </main>
      <Footer generatedAt={data.generatedAt} />
    </>
  );
}
