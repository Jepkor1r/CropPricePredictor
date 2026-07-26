import { ForecastExplorer } from "@/components/dashboard/ForecastExplorer";
import { PageHeading } from "@/components/dashboard/Shell";
import { getDashboard, getHistory } from "@/lib/data";

export const metadata = { title: "Forecasts — PriceCast" };

export default async function ForecastsPage() {
  const [data, history] = await Promise.all([getDashboard(), getHistory()]);

  return (
    <>
      <PageHeading
        title="Forecasts"
        description="Every crop-and-market series the pipeline tracks, with its 1, 2 and 4 week forecast, the range it could land in, and the message a farmer would receive. Series with too little or too stale a history are kept in the list and shown as such rather than hidden."
      />
      <ForecastExplorer
        series={data.series}
        forecasts={data.forecasts}
        history={history}
        commodities={data.commodities}
      />
    </>
  );
}
