"""Smoke tests against the real services. Run explicitly: uv run pytest -m live"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from home_dashboard.app import create_http_client
from home_dashboard.widgets.departures.insa_hafas import InsaHafasProvider
from home_dashboard.widgets.weather.open_meteo import OpenMeteoSource

pytestmark = pytest.mark.live


def test_insa_hafas_delivers_tram_departures_for_rannischer_platz() -> None:
    with create_http_client() as http:
        provider = InsaHafasProvider(http)
        now = datetime.now(ZoneInfo("Europe/Berlin"))
        departures = provider.departures("5258", now, 120, via_id="5232", products=["tram"])

    assert departures, "no departures within 2 hours (night?)"
    assert {d.product for d in departures} == {"tram"}
    assert all(d.planned.tzinfo is not None for d in departures)


def test_insa_hafas_via_keeps_only_trams_heading_towards_the_via_stop() -> None:
    # Franckeplatz -> Hauptbahnhof: trams towards Kröllwitz/Südstadt head the other way, although
    # their vehicles reach the main station later under another line number
    with create_http_client() as http:
        provider = InsaHafasProvider(http)
        now = datetime.now(ZoneInfo("Europe/Berlin"))
        departures = provider.departures("5125", now, 120, via_id="8010159", products=["tram"])

    assert departures, "no departures within 2 hours (night?)"
    assert not [d for d in departures if d.direction.endswith(("Kröllwitz", "Südstadt"))]


def test_insa_hafas_stop_search() -> None:
    with create_http_client() as http:
        matches = InsaHafasProvider(http).search_stops("Franckeplatz Halle")

    assert matches[0].id == "5125"


def test_open_meteo_delivers_a_forecast_for_halle() -> None:
    with create_http_client() as http:
        forecast = OpenMeteoSource(http, 51.48, 11.97, "Europe/Berlin").forecast()

    assert -40 < forecast.current.temperature < 45
    assert -50 < forecast.current.apparent_temperature < 50
    assert len(forecast.hours) == 48
