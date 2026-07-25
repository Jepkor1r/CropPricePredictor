"""Price service, USSD flow, SMS outbox, and the API surface."""
from __future__ import annotations

import pandas as pd
import pytest

from helpers import make_observation
from pricecast import db as DB
from pricecast import explain, prices, sms, ussd


@pytest.fixture
def stocked(conn):
    """Maize priced at three markets, all reported 'today'."""
    today = pd.Timestamp.today().normalize()
    rows = []
    for offset in range(6):
        date = str((today - pd.Timedelta(days=offset)).date())
        rows += [
            make_observation(market="Eldoret Main", county="Uasin Gishu",
                             date=date, wholesale_per_kg=50.0 - offset * 0.2),
            make_observation(market="Kitale Municipality", county="Trans Nzoia",
                             date=date, wholesale_per_kg=48.0),
            make_observation(market="Nairobi Wakulima", county="Nairobi",
                             date=date, wholesale_per_kg=62.0),
        ]
    DB.upsert_observations(conn, pd.DataFrame(rows))
    return conn


def test_price_card_ranks_by_distance_and_picks_best_price(stocked):
    card = prices.price_card(stocked, "Dry Maize", "Uasin Gishu", limit=3)
    assert [m.market for m in card.markets][0] == "Eldoret Main"
    assert card.best.market == "Nairobi Wakulima"        # best price, not nearest
    assert card.floor["floor_low"] < card.best.price_kes_per_kg


def test_price_card_reports_distance_and_age(stocked):
    card = prices.price_card(stocked, "Dry Maize", "Uasin Gishu")
    kitale = next(m for m in card.markets if m.market == "Kitale Municipality")
    assert kitale.distance_km and 50 < kitale.distance_km < 150
    assert kitale.days_old == 0


def test_stale_data_yields_no_card_rather_than_an_old_price(conn):
    DB.upsert_observations(conn, pd.DataFrame([
        make_observation(date="2011-05-02", market="Nairobi Wakulima", county="Nairobi")
    ]))
    card = prices.price_card(conn, "Dry Maize", "Nairobi")
    assert card.markets == []
    assert any("No Dry Maize prices" in w for w in card.warnings)


def test_trend_label_follows_the_data(stocked):
    change, label = prices.price_trend(
        stocked, "Dry Maize", "Uasin Gishu", "Eldoret Main"
    )
    assert label in {"rising", "falling", "steady"}
    assert change is not None


# --- USSD -------------------------------------------------------------------

def test_ussd_root_menu(stocked):
    response = ussd.UssdApp(stocked).handle("+254700000001", "")
    assert response.render().startswith("CON ")
    assert "Check price" in response.text


def test_ussd_walks_crop_then_county_then_price(stocked):
    app = ussd.UssdApp(stocked)
    phone = "+254700000001"
    assert "Choose your crop" in app.handle(phone, "1").text
    assert "your county" in app.handle(phone, "1*1").text
    screen = app.handle(phone, "1*1*1")
    assert "KES" not in screen.text or "/kg" in screen.text
    assert "floor" in screen.text.lower()
    assert not screen.close


def test_ussd_response_fits_a_screen(stocked):
    app = ussd.UssdApp(stocked)
    for text in ("", "1", "1*1", "1*1*1", "1*1*1*1", "3*1*1"):
        rendered = app.handle("+254700000001", text).render()
        assert len(rendered) <= ussd.SCREEN_LIMIT + 4


def test_price_screen_is_never_truncated(stocked):
    """A cut-off screen hides the action menu and dead-ends the session."""
    screen = ussd.UssdApp(stocked).handle("+254700000001", "1*1*1")
    rendered = screen.render()
    assert "…" not in rendered
    assert rendered.rstrip().endswith("Report offer")


def test_price_screen_survives_long_market_names(conn):
    today = str(pd.Timestamp.today().normalize().date())
    DB.upsert_observations(conn, pd.DataFrame([
        make_observation(market="Mokowe Fish Landing Site", county="Lamu",
                         date=today, wholesale_per_kg=55.0),
        make_observation(market="Garissa Soko Mugdi", county="Garissa",
                         date=today, wholesale_per_kg=52.0),
        make_observation(market="Makutano West Pokot", county="West Pokot",
                         date=today, wholesale_per_kg=48.0),
    ]))
    rendered = ussd.UssdApp(conn).handle("+254700000001", "1*1*1").render()
    assert "…" not in rendered
    assert len(rendered) <= ussd.SCREEN_LIMIT + 4


def test_ussd_sms_action_queues_a_message(stocked):
    app = ussd.UssdApp(stocked)
    response = app.handle("+254700000001", "1*1*1*1")
    assert response.close
    assert len(sms.outbox(stocked)) == 1


def test_ussd_subscription_is_recorded(stocked):
    app = ussd.UssdApp(stocked)
    response = app.handle("+254700000002", "2*1*1")
    assert response.close
    subs = DB.list_subscriptions(stocked)
    assert len(subs) == 1
    assert subs.iloc[0]["commodity"] == "Dry Maize"


def test_ussd_records_a_broker_offer_and_compares_it_to_the_floor(stocked):
    app = ussd.UssdApp(stocked)
    prompt = app.handle("+254700000003", "3*1*1")
    assert "broker offer" in prompt.text.lower() or "offer you" in prompt.text.lower()
    result = app.handle("+254700000003", "3*1*1*12")
    assert result.close
    gap = DB.farm_gate_gap(stocked)
    assert len(gap) == 1
    assert gap.iloc[0]["avg_offer"] == 12.0
    assert "below the estimated" in result.text


def test_ussd_rejects_nonsense_offers(stocked):
    app = ussd.UssdApp(stocked)
    assert "not a number" in app.handle("+254700000004", "3*1*1*abc").text
    assert DB.farm_gate_gap(stocked).empty


def test_ussd_invalid_menu_choice_ends_cleanly(stocked):
    response = ussd.UssdApp(stocked).handle("+254700000005", "9")
    assert response.close
    assert "Invalid" in response.text


def test_ussd_queries_are_logged_for_demand_telemetry(stocked):
    ussd.UssdApp(stocked).handle("+254700000006", "1*1*1")
    rows = stocked.execute("SELECT commodity, county FROM query_log").fetchall()
    assert rows == [("Dry Maize", "Nairobi")] or rows[0][0] == "Dry Maize"


# --- SMS --------------------------------------------------------------------

def test_sms_is_dry_run_without_credentials(stocked, monkeypatch):
    monkeypatch.delenv("AT_API_KEY", raising=False)
    monkeypatch.delenv("AT_USERNAME", raising=False)
    result = sms.send(stocked, "+254700000001", "hello")
    assert result.status == "queued(dry-run)"


def test_push_reaches_every_subscriber(stocked):
    DB.add_subscription(stocked, "+254700000001", "Dry Maize", "Uasin Gishu", None)
    DB.add_subscription(stocked, "+254700000002", "Dry Maize", "Trans Nzoia", None)
    results = sms.push_to_subscribers(stocked)
    assert len(results) == 2
    assert all("KES/kg" in r.message for r in results)


def test_card_sms_is_short_and_quotes_real_numbers(stocked):
    card = prices.price_card(stocked, "Dry Maize", "Uasin Gishu")
    message = explain.card_sms(card)
    assert len(message) <= explain.MAX_SMS_CHARS
    assert str(round(card.best.price_kes_per_kg)) in message
    assert "floor" in message.lower()


def test_swahili_card_sms(stocked):
    card = prices.price_card(stocked, "Dry Maize", "Uasin Gishu")
    message = explain.card_sms(card, "sw")
    assert "KES/kg" in message
    assert "shambani" in message


# --- API --------------------------------------------------------------------

@pytest.fixture
def client(stocked):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from pricecast import api

    # Override the dependency so requests hit the fixture's temp database
    # rather than the developer's real data/kamis.db.
    api.app.dependency_overrides[api.get_conn] = lambda: stocked
    yield fastapi_testclient.TestClient(api.app)
    api.app.dependency_overrides.clear()


def test_api_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["observations"] > 0


def test_api_card_returns_itemised_floor(client):
    body = client.get("/card", params={"commodity": "Dry Maize", "county": "Uasin Gishu"}).json()
    assert body["floor"]["components"]
    assert body["floor"]["floor_low"] <= body["floor"]["floor_high"]
    assert body["sms_preview"]


def test_api_netback_is_pure_arithmetic(client):
    body = client.get("/netback", params={
        "commodity": "Dry Maize", "wholesale_kes_per_kg": 50,
        "origin_county": "Trans Nzoia", "market": "Nairobi Wakulima",
        "market_county": "Nairobi",
    }).json()
    assert body["floor_low"] < 50
    assert sum(c["low"] for c in body["components"]) == pytest.approx(body["deductions_low"])


def test_api_ussd_webhook_speaks_at_protocol(client):
    response = client.post("/ussd", data={
        "sessionId": "s1", "serviceCode": "*384*1#",
        "phoneNumber": "+254700000001", "text": "",
    })
    assert response.text.startswith("CON ")


def test_api_report_endpoint_stores_the_gap(client, stocked):
    response = client.post("/reports", json={
        "phone": "+254700000009", "commodity": "Dry Maize",
        "county": "Uasin Gishu", "offer_kes_per_kg": 20.0,
    })
    assert response.status_code == 200
    assert not DB.farm_gate_gap(stocked).empty


def test_api_missing_forecast_is_404_not_a_guess(client):
    assert client.get("/forecast", params={"commodity": "Dry Maize"}).status_code == 404


def test_ussd_only_lists_crops_it_can_actually_price(conn):
    """A crop whose newest quote is from 2011 must not appear in the menu."""
    today = str(pd.Timestamp.today().normalize().date())
    DB.upsert_observations(conn, pd.DataFrame([
        make_observation(commodity="Dry Maize", date=today),
        make_observation(commodity="Tomatoes", classification="-", date="2011-01-27"),
    ]))
    menu = ussd.UssdApp(conn).handle("+254700000001", "1").text
    assert "Dry Maize" in menu
    assert "Tomatoes" not in menu


def test_ussd_says_so_when_nothing_is_fresh(conn):
    DB.upsert_observations(conn, pd.DataFrame([
        make_observation(commodity="Tomatoes", classification="-", date="2011-01-27")
    ]))
    response = ussd.UssdApp(conn).handle("+254700000001", "1")
    assert response.close
    assert "stale" in response.text.lower()
