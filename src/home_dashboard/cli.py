"""Command line entry point: `home-dashboard serve | find-stop | check-config`."""

from __future__ import annotations

import argparse
import sys

import uvicorn
import yaml
from pydantic import ValidationError

from home_dashboard.config import DEFAULT_PORT, load_config


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
        print("Keine Haltestelle gefunden.")
    for match in matches:
        print(f"{match.id:>10}  {match.name}")


def _check_config(path: str) -> int:
    """Print a summary without secrets; return a process exit code."""
    try:
        config = load_config(path)
    except FileNotFoundError:
        print(f"{path}: Datei nicht gefunden", file=sys.stderr)
        return 1
    except yaml.YAMLError as error:
        print(f"{path}: kein gültiges YAML: {error}", file=sys.stderr)
        return 1
    except ValidationError as error:
        print(f"{path}: ungültige Konfiguration", file=sys.stderr)
        for problem in error.errors():
            location = ".".join(str(part) for part in problem["loc"])
            print(f"  {location}: {problem['msg']}", file=sys.stderr)
        return 1

    stops = ", ".join(f"{s.name} ({s.walk_minutes} min)" for s in config.departures.stops)
    people = ", ".join(person.name for person in config.calendar.people)
    print(f"{path}: OK")
    print(f"  Haltestellen: {stops or '-'}")
    print(f"  Kalender: {'iCal-Adresse gesetzt' if config.calendar.ical_url else 'aus'}")
    print(
        f"  Personen: {people or '-'}; {config.calendar.everyone.label}: "
        f"{', '.join(config.calendar.everyone.match) or 'nur ohne erkannte Person'}"
    )
    return 0


if __name__ == "__main__":
    main()
