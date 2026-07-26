# 🌾 PriceCast — KAMIS Farm Price Forecasts for Smallholder Farmers

> **Machine Learning-powered weekly crop price forecasting and plain-language SMS advisories for smallholder farmers in Kenya.**

🌐 **Live Application**: [https://pricecast-nine.vercel.app/](https://pricecast-nine.vercel.app/)

---

## 📌 Overview

**PriceCast** transforms noisy, fragmented agricultural market data from the **Kenya Agricultural Market Information System (KAMIS)** into reliable, scale-invariant weekly price forecasts ($P_{10}, P_{50}, P_{90}$) and actionable SMS notifications for smallholder farmers. 

Instead of treating forecasts as black-box predictions, PriceCast enforces **rigorous honesty**:
- **Rolling-Origin Backtesting**: Evaluates model performance against a naive "last known price" baseline.
- **Automatic Fallback Tiering**: If a crop's machine learning model fails to beat the naive baseline in historical backtests, or if data is sparse/stale, predictions automatically degrade gracefully to seasonal baselines or nearest-covered-market recommendations.
- **LLM Explanation Layer**: Leverages Anthropic's Claude 3.5 Haiku to synthesize predictions, trends, and market anomalies into plain-language SMS messages (in English or Kiswahili) under strict character limits, with zero-dependency deterministic templates as a fallback.

---

## 🏗 System Architecture

```
                               ┌─────────────────────────┐
                               │   KAMIS Excel Exports   │
                               │     (data/raw/*.xls)    │
                               └────────────┬────────────┘
                                            │
                                            ▼
                                ┌───────────────────────┐
                                │   Ingest & Clean      │ (ingest.py)
                                │ Deduplicate & Normalize│
                                └────────────┬──────────┘
                                            │
                                            ▼
                                ┌───────────────────────┐
                                │   SQLite Store        │ (db.py)
                                │  data/kamis.db        │
                                └────────────┬──────────┘
                                            │
                                            ▼
                                ┌───────────────────────┐
                                │  Weekly Panel Build   │ (features.py)
                                │ Log-ratio Re-anchoring│
                                └──────┬─────────┬──────┘
                                       │         │
                   ┌───────────────────┘         └───────────────────┐
                   ▼                                                 ▼
     ┌───────────────────────────┐                     ┌───────────────────────────┐
     │  Rolling-Origin Backtest  │ (backtest.py)       │    Quantile Forecasts     │ (forecast.py)
     │ Skill vs. Naive Baseline  │                     │ LightGBM (P10, P50, P90)  │
     └─────────────┬─────────────┘                     └─────────────┬─────────────┘
                   │                                                 │
                   └───────────────────┬─────────────────────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │  Honesty Tiering Engine   │ (model.py / forecast.py)
                         │ (model / seasonal / None) │
                         └─────────────┬─────────────┘
                                       │
                                       ▼
                         ┌───────────────────────────┐
                         │   LLM SMS Advisory Layer  │ (explain.py)
                         │  Claude 3.5 Haiku / Swahili│
                         └───────────────────────────┘
```

---

## ✨ Key Features

- 🧹 **Robust Data Ingestion**: Intelligently handles messy KAMIS Excel exports, normalizes market aliases, filters temporary lock files, and collapses duplicate wholesale/retail submissions.
- 🔄 **Idempotent SQLite Database (`data/kamis.db`)**: UPSERT logic deduplicates overlapping export files, tracking incremental price/volume entries and logging file coverage.
- 📐 **Scale-Invariant Feature Engineering**: Models relative log-price ratios $\log(P_{t+h}) - \log(\text{roll4\_mean}_t)$, pooling multi-year historical data across crops and eras without nominal currency distortion.
- 🎯 **Quantile Gradient Boosting**: Trains LightGBM regressors across $P_{10}, P_{50}, P_{90}$ prediction intervals for 1-week, 2-week, and 4-week forecast horizons.
- 🛡️ **Honesty Tiering System**:
  - **`model`**: High/Medium confidence; applied only when series has $\ge 26$ weekly observations, fresh data, and beats the naive baseline in backtesting.
  - **`seasonal_fallback`**: Applied when sample size is modest ($8\text{--}25$ weeks) or the model fails to beat naive.
  - **`insufficient_data`**: Stale ($>8$ weeks missing) or sparse data; routes farmers to the nearest active market instead of rendering false predictions.
- 🚨 **Deterministic Anomaly Detection**: Flags market price spikes/dips ($>30\%$ or $>2\sigma$ deviation) relative to county and national peer markets.
- 💬 **SMS Advisory Engine**: Formats forecasts into concise SMS messages ($\le 160$ characters) in English (`en`) or Kiswahili (`sw`), using Claude 3.5 Haiku with deterministic fallback templates.

---

## 📁 Repository Structure

```
CropPricePredictor/
├── data/
│   ├── kamis.db                # SQLite database (observations, ingest_log, forecasts)
│   └── raw/                    # Raw KAMIS Excel exports (.xls / .xlsx)
├── output/                     # Generated forecast charts, backtest metrics, and report.md
├── src/
│   └── pricecast/
│       ├── __init__.py
│       ├── backtest.py         # Rolling-origin evaluation (MAPE & skill vs. naive)
│       ├── db.py               # SQLite schema definition and UPSERT logic
│       ├── explain.py          # Anthropic Claude 3.5 Haiku SMS generation & templates
│       ├── features.py         # Weekly panel construction and feature engineering
│       ├── forecast.py         # Multi-horizon forecasting & anomaly detection
│       ├── ingest.py           # KAMIS Excel parser, name normalizer, and aggregator
│       └── model.py            # LightGBM quantile trainers and fallback tiering
├── .env                        # Environment configuration (API keys)
├── market_aliases.csv          # Canonical market mapping lookup
├── requirements.txt            # Python dependencies
├── run_demo.py                 # End-to-end execution pipeline
└── README.md                   # Project documentation
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.12+**
- Virtual environment tool (`venv` or `uv`)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Jepkor1r/CropPricePredictor.git
   cd CropPricePredictor
   ```

2. **Set up virtual environment & dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables (Optional for Claude LLM)**:
   Create a `.env` file in the root directory:
   ```env
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   ```
   *(Note: If no API key is provided, the pipeline automatically uses rule-based fallback SMS templates without failing).*

---

## 💻 Usage

Run the complete end-to-end pipeline:

```bash
# Run full pipeline with Claude SMS (if API key present in .env)
python run_demo.py

# Skip Claude API and force deterministic template SMS
python run_demo.py --no-sms

# Output SMS advisories in Kiswahili
python run_demo.py --lang sw

# Specify custom raw data directory
python run_demo.py --raw-dir data/raw
```

---

## 📊 Pipeline Output & Artifacts

Upon running `python run_demo.py`, the following outputs are produced:

1. **Console Showcase**: Prints per-file ingest coverage, backtest metrics, quantile forecasts, and generated farmer SMS cards.
2. **SQLite Database (`data/kamis.db`)**:
   - `observations`: Cleaned, deduplicated historical price observations.
   - `ingest_log`: Quality report for each ingested raw file.
   - `forecasts`: Final 1-week, 2-week, and 4-week forecasts ($P_{10}, P_{50}, P_{90}$), confidence tiers, anomaly notes, and formatted SMS text.
3. **Output Directory (`output/`)**:
   - `report.md`: Complete markdown summary of coverage, backtest scores, and sample SMS messages.
   - `backtest_metrics.csv`: Detailed MAPE and skill ratio comparisons across horizons.
   - `*.png`: Visual price history and forecast range charts per market/commodity.

---

## 📈 Model Performance & Backtesting

Backtesting evaluates models using **rolling-origin temporal cross-validation** over the final ~20% of observed weeks per crop:

$$\text{Skill Ratio} = \frac{\text{MAPE}_{\text{model}}}{\text{MAPE}_{\text{naive}}}$$

- **$\text{Skill Ratio} < 1.0$**: Model outperforms the naive "last price" baseline (e.g., Dry Maize achieves $\text{Skill} = 0.68$, a 32% improvement).
- **$\text{Skill Ratio} \ge 1.0$**: Model fails to beat naive. The system automatically demotes the commodity tier to `seasonal_fallback` and flags confidence as `low`.

---

## 🔮 Phase-2 Integration Roadmap

The `forecasts` table in `data/kamis.db` serves as the clean integration contract for Phase-2 extensions:

- **REST API (FastAPI)**: Endpoints to serve forecasts (`GET /forecast`), market histories (`GET /history`), and coverage statistics.
- **USSD Interface (Africa's Talking)**: Interactive menu system (`Crop → County → Market → Forecast`) for non-smartphone users.
- **Automated SMS Push**: Scheduled dispatch of updated `sms_text` advisories to subscribed farmer phone numbers.
- **Interactive Web Dashboard**: Map visualization of market prices and anomaly warnings across Kenyan counties.
