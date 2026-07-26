import { PageHeading } from "@/components/dashboard/Shell";
import { PhoneMock } from "@/components/landing/Sections";
import { Card, CardHeader, Empty, Pill, TierBadge } from "@/components/ui/primitives";
import { getDashboard } from "@/lib/data";
import { kes, shortDate, TIER_LABEL } from "@/lib/format";

export const metadata = { title: "Messages — PriceCast" };

export default async function MessagesPage() {
  const data = await getDashboard();
  const withSms = data.forecasts.filter((f) => f.sms_text);
  const longest = withSms.reduce(
    (max, f) => Math.max(max, (f.sms_text ?? "").length),
    0,
  );

  return (
    <>
      <PageHeading
        title="Farmer messages"
        description="Claude turns each forecast into one plain-language sentence, using only the numbers the model produced. Length and figures are validated before a message would be sent, and a deterministic template stands in if the model drifts or the API is unavailable — so the pipeline never blocks on it."
      />

      {withSms.length ? (
        <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
          <div className="space-y-4">
            <Card>
              <CardHeader
                title="Generated messages"
                subtitle="Every message is tied to the forecast row it came from, so the number in the text is always the number in the database."
                right={<Pill>longest {longest} chars</Pill>}
              />
              <ul>
                {withSms.map((f) => (
                  <li key={f.series_id} className="hairline-t px-6 py-4 first:border-t-0">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="text-[14px] font-medium">
                        {f.market}
                        <span className="text-[var(--text-secondary)]"> · {f.commodity}</span>
                      </div>
                      <TierBadge tier={f.tier} label={TIER_LABEL[f.tier]} />
                    </div>

                    <p className="mt-3 rounded-2xl rounded-bl-md bg-brand-600 px-4 py-3 text-[13.5px] leading-relaxed text-white">
                      {f.sms_text}
                    </p>

                    <div className="mt-2.5 flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-secondary)]">
                      <Pill>{(f.sms_text ?? "").length} characters</Pill>
                      {f.p50 !== null ? (
                        <span className="tnum">
                          forecast {kes(f.p50, 0)} {f.unit} · last {kes(f.last_price, 0)}
                        </span>
                      ) : (
                        <span>no forecast — points to the nearest covered market</span>
                      )}
                      <span className="text-[var(--text-muted)]">
                        data through {shortDate(f.as_of)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          <div className="space-y-4">
            <div className="flex justify-center xl:sticky xl:top-24">
              <PhoneMock messages={withSms.map((f) => f.sms_text as string)} />
            </div>
          </div>
        </div>
      ) : (
        <Card>
          <Empty
            title="No messages generated yet"
            body="Run the pipeline with an API key set to generate SMS text, or use --no-sms for the deterministic template version. Either way the forecasts themselves are unaffected."
          />
        </Card>
      )}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {[
          {
            title: "Only the numbers it was given",
            body: "The prompt supplies the forecast, the range and the last price as JSON. The model is told to round to whole shillings and never invent a figure; the response is then checked to contain the forecast value before it is accepted.",
          },
          {
            title: "English or Kiswahili",
            body: "Language is chosen per subscriber. The same forecast row produces either, so nothing about the model or the database changes when a farmer switches.",
          },
          {
            title: "Phase two: USSD and scheduled SMS",
            body: "The delivery layer reads the forecasts table and nothing else. A USSD menu walks crop → county → market and returns the same sentence; a nightly job pushes updates to subscribers via Africa's Talking.",
          },
        ].map((c) => (
          <Card key={c.title}>
            <div className="px-6 py-5">
              <h3 className="text-title text-[15px]">{c.title}</h3>
              <p className="mt-2.5 text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
                {c.body}
              </p>
            </div>
          </Card>
        ))}
      </div>
    </>
  );
}
