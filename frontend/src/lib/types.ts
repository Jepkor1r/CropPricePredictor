export type Tier = "model" | "seasonal_fallback" | "insufficient_data";
export type Confidence = "high" | "medium" | "low" | "none";

/** One (commodity, classification, market, horizon) forecast row. */
export interface Forecast {
  commodity: string;
  classification: string;
  market: string;
  county: string;
  as_of: string;
  target_week_start: string;
  horizon_weeks: number;
  price_type: string;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  unit: string;
  last_price: number | null;
  last_price_date: string | null;
  tier: Tier;
  confidence: Confidence;
  anomaly_flag: number | null;
  anomaly_note: string | null;
  sms_text: string | null;
  series_id: string;
  /** Present only on pipeline revisions that record them. */
  backtest_mape?: number | null;
  skill_vs_naive?: number | null;
}

/** The 1-week row per series, enriched with its observation count. */
export interface SeriesRow extends Forecast {
  n_weeks: number | null;
}

export interface CoverageRow {
  commodity: string;
  classification: string;
  date_min: string;
  date_max: string;
  distinct_weeks: number;
  span_weeks: number;
  week_coverage_pct: number;
  n_markets: number;
  largest_gap_days: number;
  n_rows: number;
}

export interface FileRow {
  source_file: string;
  commodity: string;
  n_rows_raw: number;
  n_rows_after_agg: number;
  date_min: string;
  date_max: string;
  n_distinct_dates: number;
  n_markets: number;
  pct_missing_wholesale: number;
  pct_missing_retail: number;
  pct_missing_volume: number;
  n_unparseable_prices: number;
  n_bad_dates: number;
  hit_row_cap: number;
  loaded_at: string;
  n_price_outliers?: number;
}

export interface BacktestRow {
  commodity: string;
  horizon: number;
  n: number;
  mape_model: number;
  mape_naive: number;
  mape_seasonal: number;
  skill_vs_naive: number;
}

export interface Kpis {
  commodities: number;
  markets: number;
  counties: number;
  observations: number;
  forecastRows: number;
  series: number;
  forecastableSeries: number;
  anomalies: number;
  dateMin: string;
  dateMax: string;
  bestMape: number | null;
  hasAccuracyColumns: boolean;
}

export interface TierSummaryRow {
  tier: Tier;
  confidence: Confidence;
  count: number;
}

export interface Dashboard {
  generatedAt: string;
  kpis: Kpis;
  coverage: CoverageRow[];
  files: FileRow[];
  backtest: BacktestRow[];
  backtestBySeries: Record<string, unknown>[];
  tierSummary: TierSummaryRow[];
  commodities: string[];
  series: SeriesRow[];
  forecasts: Forecast[];
}

export type HistoryPoint = { week: string; price: number };
export type History = Record<string, HistoryPoint[]>;
