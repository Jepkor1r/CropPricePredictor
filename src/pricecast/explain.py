"""Claude explanation layer: one forecasts row in, one SMS-ready string out.

Fully decoupled from the model. Uses Claude Haiku 4.5 (cheap, fast — this is
templated short-text generation). Falls back to a deterministic template when
no API key is present or the API call fails, so the demo never blocks on
Claude.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv()
# the project's .env stores the key as CLAUDE_API_KEY
if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("CLAUDE_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = os.environ["CLAUDE_API_KEY"]

MODEL = "claude-haiku-4-5"
MAX_SMS_CHARS = 180

SYSTEM_PROMPT = """You write SMS messages for smallholder farmers in Kenya about crop prices.

Rules:
- Maximum 160 characters. Plain language, no jargon, no markdown.
- Use ONLY the numbers given in the JSON, rounded to whole KES. Never invent prices or dates.
- State the trend direction (rising / steady / falling) by comparing the forecast to the last price.
- Prices are KES per Kg unless the unit says otherwise.
- If tier is "insufficient_data": say there is not enough data for this market and point to the nearest covered market given in the JSON.
- If anomaly_note is present, add one short clause noting the price is unusually high/low vs nearby markets.
- Do not advise holding or selling beyond "prices expected to rise/fall".
- If language is "sw", write in Kiswahili; otherwise English.

Reply with the SMS text only."""


def _trend(row: dict) -> str:
    if not row.get("p50") or not row.get("last_price"):
        return "unknown"
    change = (row["p50"] - row["last_price"]) / row["last_price"]
    if change > 0.03:
        return "rising"
    if change < -0.03:
        return "falling"
    return "steady"


def fallback_template(row: dict, language: str = "en") -> str:
    market, com = row["market"], row["commodity"]
    if row["tier"] == "insufficient_data":
        alt = row.get("nearest_market")
        if language == "sw":
            msg = f"{market}: hakuna data ya kutosha ya bei ya {com}."
            if alt:
                msg += f" Jaribu soko la {alt}."
        else:
            msg = f"{market}: not enough {com} price data for a forecast."
            if alt:
                msg += f" Nearest covered market: {alt}."
        return msg[:MAX_SMS_CHARS]

    p50, last = round(row["p50"]), round(row["last_price"])
    lo, hi = round(row["p10"]), round(row["p90"])
    trend = _trend(row)
    if language == "sw":
        tr = {"rising": "inapanda", "falling": "inashuka", "steady": "thabiti"}.get(trend, "")
        msg = (f"{market} {com}: sasa {last} KES/kg, wiki {row['horizon_weeks']} "
               f"ijayo ~{p50} KES/kg ({lo}-{hi}). Bei {tr}.")
    else:
        msg = (f"{market} {com} ({row['price_type']}): now {last} KES/kg, "
               f"expected ~{p50} KES/kg in {row['horizon_weeks']}wk ({lo}-{hi}). "
               f"Trend: {trend}.")
    if row.get("anomaly_note"):
        msg += f" Note: price here {row['anomaly_note'].split(' (')[0]} vs nearby markets."
    return msg[:MAX_SMS_CHARS]


def sms_for(row: dict, language: str = "en") -> str:
    """Generate the SMS via Claude; validate; fall back to the template."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return fallback_template(row, language)
    try:
        import anthropic
        client = anthropic.Anthropic()
        payload = {
            k: row.get(k) for k in (
                "commodity", "classification", "market", "county", "price_type",
                "last_price", "last_price_date", "p10", "p50", "p90", "unit",
                "horizon_weeks", "target_week_start", "tier", "confidence",
                "anomaly_note", "nearest_market",
            )
        }
        payload["trend"] = _trend(row)
        payload["language"] = language
        messages = [{"role": "user", "content": json.dumps(payload)}]

        for attempt in range(2):
            resp = client.messages.create(
                model=MODEL, max_tokens=200,
                system=SYSTEM_PROMPT, messages=messages,
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if _valid(text, row):
                return text
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content":
                    f"That message was invalid (must be <= {MAX_SMS_CHARS} chars and "
                    f"contain the forecast figure {round(row['p50']) if row.get('p50') else ''}). "
                    "Rewrite it following all rules."},
            ]
        return fallback_template(row, language)
    except Exception as exc:  # any API failure -> deterministic path
        print(f"  [explain] Claude call failed ({exc.__class__.__name__}); using template")
        return fallback_template(row, language)


def _valid(text: str, row: dict) -> bool:
    if not text or len(text) > MAX_SMS_CHARS:
        return False
    if row["tier"] == "insufficient_data":
        return True
    return str(round(row["p50"])) in text.replace(",", "")
