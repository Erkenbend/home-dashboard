"""FastAPI application factory (composition root)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from home_dashboard import REPOSITORY_URL, formatting
from home_dashboard.cache import TtlCache
from home_dashboard.clock import Clock, SystemClock
from home_dashboard.config import AppConfig, config_path_from_env, load_config
from home_dashboard.widgets.calendar.ical_source import IcalCalendarSource
from home_dashboard.widgets.calendar.service import CalendarService
from home_dashboard.widgets.calendar.source import CalendarSource
from home_dashboard.widgets.departures.insa_hafas import InsaHafasProvider
from home_dashboard.widgets.departures.provider import DepartureProvider
from home_dashboard.widgets.departures.service import DeparturesService
from home_dashboard.widgets.status.http_check import HttpHealthCheck
from home_dashboard.widgets.status.service import StatusService
from home_dashboard.widgets.status.source import HealthCheck
from home_dashboard.widgets.weather.open_meteo import OpenMeteoSource
from home_dashboard.widgets.weather.service import WeatherService
from home_dashboard.widgets.weather.source import WeatherSource

PACKAGE_DIR = Path(__file__).parent
HTTP_TIMEOUT = httpx.Timeout(10.0)
USER_AGENT = "home-dashboard (private wall display)"


def static_url_builder(directory: Path) -> Callable[[str], str]:
    """URLs for static assets with a content hash, so browsers never keep using a stale copy.

    StaticFiles sends no Cache-Control, so browsers cache heuristically (kiosk WebViews for hours
    to days) and combine old CSS/JS with new HTML. The hash changes the URL whenever the file
    changes.
    """
    versions = {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        for path in directory.rglob("*")
        if path.is_file()
    }

    def static_url(name: str) -> str:
        return f"/static/{name}?v={versions[name]}"

    return static_url


def create_http_client() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": USER_AGENT})


def create_app(
    config: AppConfig,
    clock: Clock | None = None,
    departure_provider: DepartureProvider | None = None,
    calendar_source: CalendarSource | None = None,
    weather_source: WeatherSource | None = None,
    health_check: HealthCheck | None = None,
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
    weather = None
    if location := config.weather_location:
        weather = WeatherService(
            config.weather,
            weather_source or OpenMeteoSource(http, *location, config.timezone),
            clock,
            cache,
        )
    status = None
    if config.status.services:
        status = StatusService(
            config.status,
            health_check or HttpHealthCheck(http, config.status.timeout_seconds),
            clock,
        )

    app = FastAPI(title="Home Dashboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["time"] = formatting.format_time
    templates.env.filters["long_date"] = formatting.format_long_date
    templates.env.globals["config"] = config
    templates.env.globals["repository_url"] = REPOSITORY_URL
    templates.env.globals["static_url"] = static_url_builder(PACKAGE_DIR / "static")

    def departures_context() -> dict:
        return {"boards": departures.boards(), "show_departures": bool(config.departures.stops)}

    def calendar_context() -> dict:
        return {"calendar": calendar.view() if calendar else None}

    def weather_context() -> dict:
        return {"weather": weather.view() if weather else None}

    def status_context() -> dict:
        return {"status": status.view() if status else None}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        context = {
            "now": clock.now(),
            **status_context(),
            **departures_context(),
            **calendar_context(),
            **weather_context(),
        }
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

    @app.get("/widgets/weather", response_class=HTMLResponse)
    def weather_widget(request: Request) -> HTMLResponse:
        if weather is None:
            return HTMLResponse("", status_code=404)
        return templates.TemplateResponse(request, "widgets/weather.html", weather_context())

    @app.get("/widgets/status", response_class=HTMLResponse)
    def status_widget(request: Request) -> HTMLResponse:
        if status is None:
            return HTMLResponse("", status_code=404)
        return templates.TemplateResponse(request, "widgets/status.html", status_context())

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_app_from_env() -> FastAPI:
    """Entry point for uvicorn (`--factory`): reads the config path from the environment."""
    return create_app(load_config(config_path_from_env()))
