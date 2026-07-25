"""USSD menu flow (Africa's Talking compatible), as a pure function.

Africa's Talking POSTs `sessionId, phoneNumber, text` where `text` is the full
`1*3*2` accumulation of everything the farmer has pressed, and expects a body
beginning with `CON ` (keep the session open) or `END ` (close it). That makes
the whole flow a pure function of (tokens, database), which is why it lives
here as `handle()` and not inside a web handler: it is fully testable and
demoable offline, with no network, no ngrok, and no telco account.

Latency budget is the reason nothing here trains or calls an LLM. Every screen
is a handful of indexed SQLite reads plus arithmetic from the registries.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import db, explain, prices
from .config import PILOT_COMMODITIES

PAGE_SIZE = 8
SCREEN_LIMIT = 182          # AT truncates beyond ~182 chars per screen


@dataclass
class UssdResponse:
    text: str
    close: bool = False

    def render(self) -> str:
        prefix = "END " if self.close else "CON "
        body = self.text.strip()
        if len(body) > SCREEN_LIMIT:
            body = body[: SCREEN_LIMIT - 1].rstrip() + "…"
        return prefix + body


def _con(text: str) -> UssdResponse:
    return UssdResponse(text, close=False)


def _end(text: str) -> UssdResponse:
    return UssdResponse(text, close=True)


def parse_tokens(text: str | None) -> list[str]:
    return [t for t in (text or "").split("*") if t != ""]


def _paged_choice(tokens: list[str], items: list) -> tuple[object | None, int, int, bool]:
    """Walk tokens for a paged list. Returns (choice, consumed, page, invalid)."""
    page = 0
    for i, token in enumerate(tokens):
        if token == "0":
            if (page + 1) * PAGE_SIZE < len(items):
                page += 1
            continue
        if token.isdigit():
            index = int(token) - 1
            window = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
            if 0 <= index < len(window):
                return window[index], i + 1, page, False
            return None, i + 1, page, True
        return None, i + 1, page, True
    return None, len(tokens), page, False


def _render_list(title: str, items: list[str], page: int) -> str:
    window = items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]
    lines = [title]
    for i, label in enumerate(window, start=1):
        lines.append(f"{i}. {label}")
    if (page + 1) * PAGE_SIZE < len(items):
        lines.append("0. More")
    return "\n".join(lines)


class UssdApp:
    """Stateless handler over an open SQLite connection."""

    def __init__(self, conn: sqlite3.Connection, reference_date: str | None = None,
                 language: str = "en", log: bool = True):
        self.conn = conn
        self.reference_date = reference_date
        self.language = language
        self.log = log

    # -- catalogue -----------------------------------------------------------
    def crops(self) -> list[str]:
        """Only crops we can actually price today.

        Offering a crop whose newest quote is from 2011 dead-ends the farmer
        two screens later, having spent their airtime. A shorter honest menu
        beats a long menu of dead ends.
        """
        available = prices.available_commodities(
            self.conn,
            max_age_days=prices.DEFAULT_MAX_AGE_DAYS,
            reference_date=self.reference_date,
        )
        ordered = [c for c in PILOT_COMMODITIES if c in available]
        return ordered + [c for c in available if c not in ordered]

    def counties(self, commodity: str) -> list[str]:
        return prices.available_counties(self.conn, commodity)

    # -- entry point ---------------------------------------------------------
    def handle(self, phone: str, text: str | None) -> UssdResponse:
        tokens = parse_tokens(text)
        if not tokens:
            return _con(
                "PriceCast: know your crop's value\n"
                "1. Check price near me\n"
                "2. Get price alerts\n"
                "3. Report a broker offer"
            )
        choice = tokens[0]
        rest = tokens[1:]
        if choice == "1":
            return self._flow_price(phone, rest)
        if choice == "2":
            return self._flow_subscribe(phone, rest)
        if choice == "3":
            return self._flow_report(phone, rest)
        return _end("Invalid choice. Dial again.")

    # -- shared crop/county selection ---------------------------------------
    def _select_crop_county(self, tokens: list[str]):
        crops = self.crops()
        if not crops:
            return None, _end(
                "No crop has a price fresh enough to quote today. "
                "We would rather say nothing than quote a stale price."
            )
        crop, consumed, page, invalid = _paged_choice(tokens, crops)
        if invalid:
            return None, _end("Invalid choice. Dial again.")
        if crop is None:
            return None, _con(_render_list("Choose your crop:", crops, page))

        counties = self.counties(crop)
        if not counties:
            return None, _end(f"No {crop} markets on file yet.")
        county, consumed2, page2, invalid2 = _paged_choice(tokens[consumed:], counties)
        if invalid2:
            return None, _end("Invalid choice. Dial again.")
        if county is None:
            return None, _con(_render_list(f"{crop} - your county:", counties, page2))
        return (crop, county, tokens[consumed + consumed2 :]), None

    # -- flow 1: price -------------------------------------------------------
    def _flow_price(self, phone: str, tokens: list[str]) -> UssdResponse:
        selection, response = self._select_crop_county(tokens)
        if response is not None:
            return response
        crop, county, rest = selection

        card = prices.price_card(
            self.conn, crop, county, limit=3, reference_date=self.reference_date
        )
        if self.log:
            db.log_query(self.conn, phone, "ussd", crop, county,
                         card.best.market if card.best else None)

        if not card.markets:
            return _end(
                f"No {crop} prices reported near {county} in the last 3 weeks. "
                "We only show prices we actually have."
            )

        if not rest:
            return _con(self._price_screen(card))

        action = rest[0]
        if action == "1":
            message = explain.card_sms(card, self.language)
            from . import sms

            sms.send(self.conn, phone, message)
            return _end(f"Sent to {phone}. Check your SMS for the full price and floor.")
        if action == "2":
            # crop/county are already chosen; hand them straight to the report flow
            return self._flow_report(phone, ["__preset__", *rest[1:]],
                                     preselected=(crop, county), card=card)
        return _end("Invalid choice. Dial again.")

    def _price_screen(self, card) -> str:
        """Build the densest screen that still fits without being truncated.

        A truncated USSD screen ('2. R…') hides the action menu and dead-ends
        the session, so market rows are added only while the budget allows and
        the footer is reserved up front.
        """
        footer = "1. SMS me  2. Report offer"
        header = f"{card.commodity} near {card.origin_county}:"
        floor_line = ""
        if card.floor:
            floor_line = (
                f"Floor {card.floor['floor_low']:.0f}-{card.floor['floor_high']:.0f}/kg "
                "after costs"
            )
        budget = SCREEN_LIMIT - len(header) - len(footer) - len(floor_line) - 4

        rows = []
        for market in card.markets:
            name = market.market if len(market.market) <= 14 else market.market[:13] + "."
            distance = f" {market.distance_km:.0f}km" if market.distance_km else ""
            line = f"{name}{distance} {market.price_kes_per_kg:.0f}/kg {market.days_old}d"
            if len(line) + 1 > budget:
                break
            rows.append(line)
            budget -= len(line) + 1

        parts = [header, *rows]
        if floor_line:
            parts.append(floor_line)
        parts.append(footer)
        return "\n".join(parts)

    # -- flow 2: subscribe ---------------------------------------------------
    def _flow_subscribe(self, phone: str, tokens: list[str]) -> UssdResponse:
        selection, response = self._select_crop_county(tokens)
        if response is not None:
            return response
        crop, county, _rest = selection
        db.add_subscription(self.conn, phone, crop, county, None, self.language)
        return _end(
            f"Subscribed. You will get a weekly {crop} price SMS for {county}. "
            "Dial again and choose 2 to change."
        )

    # -- flow 3: report a broker offer --------------------------------------
    def _flow_report(self, phone: str, tokens: list[str], preselected=None,
                     card=None) -> UssdResponse:
        if tokens and tokens[0] == "__preset__" and preselected:
            crop, county = preselected
            rest = tokens[1:]
        else:
            selection, response = self._select_crop_county(tokens)
            if response is not None:
                return response
            crop, county, rest = selection

        if not rest:
            return _con(
                f"{crop} in {county}\nWhat did the broker offer you, in KES per kg?\n"
                "(enter a number)"
            )
        try:
            offer = float(rest[0])
        except ValueError:
            return _end("That was not a number. Dial again to report.")
        if offer <= 0 or offer > 100000:
            return _end("That amount looks wrong. Dial again to report.")

        if card is None:
            card = prices.price_card(
                self.conn, crop, county, limit=3, reference_date=self.reference_date
            )
        floor = card.floor or {}
        db.add_farm_gate_report(
            self.conn,
            phone=phone, commodity=crop, county=county,
            market=card.best.market if card.best else None,
            offer_kes_per_kg=offer, sold=None,
            reference_wholesale=card.best.price_kes_per_kg if card.best else None,
            reference_floor_low=floor.get("floor_low"),
            reference_floor_high=floor.get("floor_high"),
            channel="ussd",
        )
        if floor.get("floor_low") is not None and offer < floor["floor_low"]:
            gap = floor["floor_low"] - offer
            return _end(
                f"Recorded: {offer:.0f}/kg. That is {gap:.0f}/kg below the estimated "
                f"floor of {floor['floor_low']:.0f}-{floor['floor_high']:.0f}/kg. Thank you."
            )
        return _end(f"Recorded: {offer:.0f}/kg for {crop} in {county}. Thank you.")


def handle(conn: sqlite3.Connection, phone: str, text: str | None,
           reference_date: str | None = None) -> str:
    """Convenience wrapper returning the raw AT response body."""
    return UssdApp(conn, reference_date=reference_date).handle(phone, text).render()
