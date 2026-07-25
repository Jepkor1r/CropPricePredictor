"""Farmer-facing message rendering.

Deterministic templates are the default and the only thing on the request path.
An LLM is optional enrichment for the SMS channel: USSD has a hard ~5 second
telecom timeout, an LLM call per screen would blow both the latency budget and
the unit economics, and a price message is a fixed-shape sentence that does not
need generation. Claude is therefore used to phrase *push* SMS when a key is
present, always validated against the underlying numbers, and always with a
template fallback.
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

load_dotenv()
if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("CLAUDE_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = os.environ["CLAUDE_API_KEY"]

MODEL = "claude-haiku-4-5"
MAX_SMS_CHARS = 320          # two GSM-7 segments; single segment where possible

SYSTEM_PROMPT = """You write SMS messages for smallholder farmers in Kenya about crop prices.

Rules:
- Maximum 300 characters. Plain language, no jargon, no markdown.
- Use ONLY the numbers given in the JSON, rounded to whole KES. Never invent prices or dates.
- Always state the market name and how old the price is.
- If a farm-gate floor range is given, present it as a range and say it is an
  estimate after transport and levies.
- State the trend direction (rising / steady / falling) only if it is given.
- Do not tell the farmer to hold or sell. Do not promise future prices.
- If language is "sw", write in Kiswahili; otherwise English.

Reply with the SMS text only."""


# --- price cards ------------------------------------------------------------

def card_sms(card, language: str = "en") -> str:
    """Deterministic SMS for a price card (the transparency product)."""
    if not card.markets:
        if language == "sw":
            return f"Hakuna bei mpya ya {card.commodity} karibu na {card.origin_county}."
        return f"No recent {card.commodity} prices near {card.origin_county}."

    best = card.best
    age = "today" if best.days_old == 0 else f"{best.days_old}d ago"
    age_sw = "leo" if best.days_old == 0 else f"siku {best.days_old} zilizopita"
    floor = card.floor
    if language == "sw":
        msg = (
            f"{card.commodity} {best.market}: {best.price_kes_per_kg:.0f} KES/kg ({age_sw})."
        )
        if floor:
            msg += (
                f" Bei ya shambani inakadiriwa {floor['floor_low']:.0f}-"
                f"{floor['floor_high']:.0f} KES/kg baada ya usafiri na ushuru."
            )
        if best.trend_label == "rising":
            msg += " Bei inapanda."
        elif best.trend_label == "falling":
            msg += " Bei inashuka."
    else:
        msg = f"{card.commodity} at {best.market}: {best.price_kes_per_kg:.0f} KES/kg ({age})."
        if floor:
            msg += (
                f" Est. farm-gate floor {floor['floor_low']:.0f}-{floor['floor_high']:.0f} "
                "KES/kg after transport & levies."
            )
        if best.trend_label in {"rising", "falling"}:
            msg += f" Trend: {best.trend_label}."
    return msg[:MAX_SMS_CHARS]


def card_payload(card) -> dict:
    best = card.best
    return {
        "commodity": card.commodity,
        "county": card.origin_county,
        "market": best.market if best else None,
        "price_kes_per_kg": best.price_kes_per_kg if best else None,
        "price_date": best.price_date if best else None,
        "days_old": best.days_old if best else None,
        "trend": best.trend_label if best else None,
        "distance_km": best.distance_km if best else None,
        "floor_low": (card.floor or {}).get("floor_low"),
        "floor_high": (card.floor or {}).get("floor_high"),
        "other_markets": [
            {"market": m.market, "price": m.price_kes_per_kg, "days_old": m.days_old}
            for m in card.markets[1:3]
        ],
    }


# --- forecasts --------------------------------------------------------------

def _trend(row: dict) -> str:
    if not row.get("p50") or not row.get("last_price"):
        return "unknown"
    change = (row["p50"] - row["last_price"]) / row["last_price"]
    if change > 0.03:
        return "rising"
    if change < -0.03:
        return "falling"
    return "steady"


def forecast_template(row: dict, language: str = "en") -> str:
    market, commodity = row["market"], row["commodity"]
    if row["tier"] == "insufficient_data":
        alt = row.get("nearest_market")
        if language == "sw":
            msg = f"{market}: hakuna data ya kutosha ya bei ya {commodity}."
            if alt:
                msg += f" Jaribu soko la {alt}."
        else:
            msg = f"{market}: not enough recent {commodity} data for a forecast."
            if alt:
                msg += f" Nearest covered market: {alt}."
        return msg[:MAX_SMS_CHARS]

    p50, last = round(row["p50"]), round(row["last_price"])
    low, high = round(row["p10"]), round(row["p90"])
    trend = _trend(row)
    hedge = "" if row["tier"] == "model" else " (baseline estimate)"
    if language == "sw":
        translated = {"rising": "inapanda", "falling": "inashuka", "steady": "thabiti"}
        msg = (
            f"{market} {commodity}: sasa {last} KES/kg, wiki {row['horizon_weeks']} "
            f"ijayo ~{p50} KES/kg ({low}-{high}). Bei {translated.get(trend, '')}."
        )
    else:
        msg = (
            f"{market} {commodity} ({row['price_type']}): now {last} KES/kg, "
            f"expected ~{p50} KES/kg in {row['horizon_weeks']}wk ({low}-{high}){hedge}. "
            f"Trend: {trend}."
        )
    if row.get("anomaly_note"):
        msg += f" Note: price here {row['anomaly_note'].split(' (')[0]} vs nearby markets."
    return msg[:MAX_SMS_CHARS]


# --- optional LLM phrasing --------------------------------------------------

def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def sms_for(row: dict, language: str = "en", use_llm: bool = True) -> str:
    """Claude-phrased forecast SMS, validated; deterministic template otherwise."""
    if not use_llm or not llm_available():
        return forecast_template(row, language)
    try:
        import anthropic

        client = anthropic.Anthropic()
        payload = {
            key: row.get(key)
            for key in (
                "commodity", "classification", "market", "county", "price_type",
                "last_price", "last_price_date", "p10", "p50", "p90", "unit",
                "horizon_weeks", "target_week_start", "tier", "confidence",
                "anomaly_note", "nearest_market",
            )
        }
        payload["trend"] = _trend(row)
        payload["language"] = language
        messages = [{"role": "user", "content": json.dumps(payload)}]

        for _ in range(2):
            response = client.messages.create(
                model=MODEL, max_tokens=300, system=SYSTEM_PROMPT, messages=messages
            )
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            if _valid_forecast(text, row):
                return text
            messages += [
                {"role": "assistant", "content": text},
                {"role": "user", "content": (
                    f"That message was invalid (max {MAX_SMS_CHARS} chars and it must contain "
                    f"the figure {round(row['p50']) if row.get('p50') else ''}). Rewrite it."
                )},
            ]
        return forecast_template(row, language)
    except Exception as exc:  # noqa: BLE001 - any API failure falls back
        print(f"  [explain] Claude call failed ({exc.__class__.__name__}); using template")
        return forecast_template(row, language)


def card_sms_llm(card, language: str = "en", use_llm: bool = True) -> str:
    if not use_llm or not llm_available():
        return card_sms(card, language)
    try:
        import anthropic

        client = anthropic.Anthropic()
        payload = card_payload(card)
        payload["language"] = language
        response = client.messages.create(
            model=MODEL, max_tokens=300, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if _valid_card(text, card):
            return text
        return card_sms(card, language)
    except Exception as exc:  # noqa: BLE001
        print(f"  [explain] Claude call failed ({exc.__class__.__name__}); using template")
        return card_sms(card, language)


def _valid_forecast(text: str, row: dict) -> bool:
    if not text or len(text) > MAX_SMS_CHARS:
        return False
    if row["tier"] == "insufficient_data":
        return True
    return str(round(row["p50"])) in text.replace(",", "")


def _valid_card(text: str, card) -> bool:
    if not text or len(text) > MAX_SMS_CHARS:
        return False
    if not card.best:
        return True
    return str(round(card.best.price_kes_per_kg)) in text.replace(",", "")


# Backwards-compatible alias used by the v1 demo script.
fallback_template = forecast_template
