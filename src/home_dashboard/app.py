"""FastAPI application factory (composition root)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from home_dashboard import formatting
from home_dashboard.clock import Clock, SystemClock
from home_dashboard.config import AppConfig, config_path_from_env, load_config

PACKAGE_DIR = Path(__file__).parent


def create_app(config: AppConfig, clock: Clock | None = None) -> FastAPI:
    clock = clock or SystemClock(config.timezone)

    app = FastAPI(title="Home Dashboard", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["time"] = formatting.format_time
    templates.env.filters["long_date"] = formatting.format_long_date

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html", {"now": clock.now()})

    @app.get("/widgets/clock", response_class=HTMLResponse)
    def clock_widget(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "widgets/clock.html", {"now": clock.now()})

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def create_app_from_env() -> FastAPI:
    """Entry point for uvicorn (`--factory`): reads the config path from the environment."""
    return create_app(load_config(config_path_from_env()))
