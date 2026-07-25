"""SMS delivery via Africa's Talking, with a dry-run outbox by default.

No credentials means no network call: messages land in an `sms_outbox` table
and are printed. That keeps the demo, the tests, and a plane-mode laptop all
working, and it means a misconfigured cron can never spam real farmers.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

import pandas as pd

from . import explain, prices

OUTBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS sms_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  phone TEXT NOT NULL,
  message TEXT NOT NULL,
  status TEXT NOT NULL,
  provider_id TEXT,
  sent_at TEXT DEFAULT (datetime('now'))
);
"""


@dataclass
class SendResult:
    phone: str
    message: str
    status: str          # 'sent' | 'queued(dry-run)' | 'failed'
    provider_id: str | None = None


def _ensure_outbox(conn: sqlite3.Connection) -> None:
    conn.executescript(OUTBOX_SCHEMA)


def credentials() -> tuple[str | None, str | None, str | None]:
    return (
        os.environ.get("AT_USERNAME"),
        os.environ.get("AT_API_KEY"),
        os.environ.get("AT_SENDER_ID"),
    )


def configured() -> bool:
    username, api_key, _ = credentials()
    return bool(username and api_key)


def send(conn: sqlite3.Connection, phone: str, message: str) -> SendResult:
    _ensure_outbox(conn)
    status, provider_id = "queued(dry-run)", None
    if configured():
        try:
            status, provider_id = _send_live(phone, message)
        except Exception as exc:  # noqa: BLE001 - never let delivery break a flow
            status, provider_id = f"failed:{exc.__class__.__name__}", None
    conn.execute(
        "INSERT INTO sms_outbox (phone, message, status, provider_id) VALUES (?,?,?,?)",
        (phone, message, status, provider_id),
    )
    conn.commit()
    return SendResult(phone, message, status, provider_id)


def _send_live(phone: str, message: str) -> tuple[str, str | None]:
    import africastalking  # type: ignore[import-not-found]

    username, api_key, sender = credentials()
    africastalking.initialize(username, api_key)
    response = africastalking.SMS.send(message, [phone], sender_id=sender)
    recipients = response.get("SMSMessageData", {}).get("Recipients", [])
    if recipients:
        return recipients[0].get("status", "sent"), recipients[0].get("messageId")
    return "sent", None


def outbox(conn: sqlite3.Connection, limit: int = 20) -> pd.DataFrame:
    _ensure_outbox(conn)
    return pd.read_sql_query(
        "SELECT phone, status, message, sent_at FROM sms_outbox "
        "ORDER BY id DESC LIMIT ?", conn, params=[limit],
    )


def push_to_subscribers(
    conn: sqlite3.Connection,
    reference_date: str | None = None,
    use_llm: bool = False,
    limit: int | None = None,
) -> list[SendResult]:
    """Broadcast the current price card to every active subscription."""
    from . import db

    subs = db.list_subscriptions(conn)
    if subs.empty:
        return []
    if limit:
        subs = subs.head(limit)
    results = []
    for row in subs.to_dict("records"):
        card = prices.price_card(
            conn, row["commodity"], row["county"], limit=3, reference_date=reference_date
        )
        message = explain.card_sms_llm(card, row.get("language", "en"), use_llm=use_llm)
        results.append(send(conn, row["phone"], message))
    return results
