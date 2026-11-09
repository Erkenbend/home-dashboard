"""FastAPI application factory (composition root)."""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from home_dashboard import formatting
from home_dashboard.cache import TtlCache
from home_dashboard.clock import Clock, SystemClock
from home_dashboard.config import AppConfig, config_path_from_env, load_config
from home_dashboard.widgets.calendar.ical_source import IcalCalendarSource
from home_dashboard.widgets.calendar.service import CalendarService
from home_dashboard.widgets.calendar.source import CalendarSource
from home_dashboard.widgets.departures.insa_hafas import InsaHafasProvider
from home_dashboard.widgets.departures.provider import DepartureProvider
from home_dashboard.widgets.departures.service import DeparturesService

PACKAGE_DIR = Path(__file__).parent
HTTP_TIMEOUT = httpx.Timeout(10.0)
USER_AGENT = "home-dashboard (private wall display)"


def create_http_client() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})


def create_app(
    config: AppConfig,
    clock: Clock | None = None,
    departure_provider: DepartureProvider | None = None,
    calendar_source: CalendarSource | None = None,
) -> FastAPI:
    clock = clock or SystemClock(config.timezone)
    cache = TtlCache(clock)
    http = create_http_client()
    departures = DeparturesService(
        config.departures,
        departure_provider or InsaHafasProvider(http),
        clock,
        cache,
    )
    if calendar_source is None and config.calendar.ical_url:
        calendar_source = IcalCalendarSource(http, config.calendar.ical_url, config.timezone)
    calendar = (
        CalendarService(config.calendar, calendar_source, clock, cache, config.timezone)
        if calendar_source is not None
        else None
    )

    app = FastAPI(title="Home Dashboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["time"] = formatting.format_time
    templates.env.filters["long_date"] = formatting.format_long_date

    def departures_context() -> dict:
        return {"boards": departures.boards(), "show_departures": bool(config.departures.stops)}

    def calendar_context() -> dict:
        return {"calendar": calendar.view() if calendar else None}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        context = {"now": clock.now(), **departures_context(), **calendar_context()}
        return templates.TemplateResponse(request, "index.html", context)

    @app.get("/widgets/clock", response_class=HTMLResponse)
    def clock_widget(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "widgets/clock.html", {"now": clock.now()})

    @app.get("/widgets/departures", response_class=HTMLResponse)
    def departures_widget(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "widgets/departures.html", departures_context())

    @app.get("/widgets/calendar", response_class=HTMLResponse)
    def calendar_widget(request: Request) -> HTMLResponse:
        if calendar is None:
            return HTMLResponse("", status_code=404)
        return templates.TemplateResponse(request, "widgets/calendar.html", calendar_context())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_app_from_env() -> FastAPI:
    """Entry point for uvicorn (`--factory`): reads the config path from the environment."""
    return create_app(load_config(config_path_from_env()))
