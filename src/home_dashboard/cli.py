"""Command line entry point: `home-dashboard serve | find-stop | check-config`."""

from __future__ import annotations

import argparse
import sys

import uvicorn
import yaml
from pydantic import ValidationError

from home_dashboard.config import DEFAULT_PORT, AppConfig, load_config


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="home-dashboard")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the web server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")

    find_stop = commands.add_parser("find-stop", help="look up stop ids for config.yaml")
    find_stop.add_argument("query", help='e.g. "Rannischer Platz Halle"')

    check_config = commands.add_parser("check-config", help="validate a config file")
    check_config.add_argument("path", nargs="?", default="config.yaml")

    args = parser.parse_args(argv)
    if args.command == "serve":
        uvicorn.run(
            "home_dashboard.app:create_app_from_env",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    elif args.command == "find-stop":
        _find_stop(args.query)
    elif args.command == "check-config":
        sys.exit(_check_config(args.path))


def _find_stop(query: str) -> None:
    from home_dashboard.app import create_http_client
    from home_dashboard.widgets.departures.insa_hafas import InsaHafasProvider

    with create_http_client() as http:
        matches = InsaHafasProvider(http).search_stops(query)
    if not matches:
        print("No stop found.")
    for match in matches:
        print(f"{match.id:>10}  {match.name}")


def _check_config(path: str) -> int:
    """Print a summary without secrets; return a process exit code."""
    try:
        config = load_config(path)
    except FileNotFoundError:
        print(f"{path}: file not found", file=sys.stderr)
        return 1
    except yaml.YAMLError as error:
        print(f"{path}: not valid YAML: {error}", file=sys.stderr)
        return 1
    except ValidationError as error:
        print(f"{path}: invalid configuration", file=sys.stderr)
        for problem in error.errors():
            location = ".".join(str(part) for part in problem["loc"])
            print(f"  {location}: {problem['msg']}", file=sys.stderr)
        return 1

    stops = ", ".join(f"{s.name} ({s.walk_minutes} min)" for s in config.departures.stops)
    people = ", ".join(person.name for person in config.calendar.people)
    print(f"{path}: OK")
    print(f"  Stops: {stops or '-'}")
    print(f"  Calendar: {'iCal address set' if config.calendar.ical_url else 'off'}")
    print(f"  Birthdays: {_birthdays_summary(config)}")
    print(f"  Weather: {_weather_summary(config)}")
    services = ", ".join(service.name for service in config.status.services)
    print(f"  Services: {services or '-'}")
    print(
        f"  People: {people or '-'}; everyone: "
        f"{', '.join(config.calendar.everyone.match) or 'only without a recognized person'}"
    )
    display, departures, calendar = config.display, config.departures, config.calendar
    weather = config.weather
    reload = f"{display.page_reload_hours:g} h" if display.page_reload_hours else "off"
    print(
        f"  Refresh: clock {display.clock_refresh_seconds} s, "
        f"departures {departures.refresh_seconds} s (fetch {departures.fetch_seconds} s), "
        f"calendar {calendar.refresh_seconds} s (fetch {calendar.fetch_seconds} s), "
        f"birthdays {config.birthdays.refresh_seconds} s "
        f"(fetch {config.birthdays.fetch_seconds} s), "
        f"weather {weather.refresh_seconds} s (fetch {weather.fetch_seconds} s), "
        f"services {config.status.refresh_seconds} s (check {config.status.check_seconds} s), "
        f"page reload {reload}"
    )
    return 0


def _birthdays_summary(config: AppConfig) -> str:
    if not config.birthdays.enabled:
        return "off"
    if config.birthdays_url is None:
        return "off (no iCal address)"
    return f"iCal address set, {config.birthdays.days} days"


def _weather_summary(config: AppConfig) -> str:
    if not config.weather.enabled:
        return "off"
    if config.weather_location is None:
        return "off (home.lat / home.lon missing)"
    return "on"


if __name__ == "__main__":
    main()
