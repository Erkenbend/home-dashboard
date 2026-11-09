"""Command line entry point: `home-dashboard serve | find-stop`."""

from __future__ import annotations

import argparse

import uvicorn

from home_dashboard.config import DEFAULT_PORT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="home-dashboard")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the web server")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (dev)")

    find_stop = commands.add_parser("find-stop", help="look up stop ids for config.yaml")
    find_stop.add_argument("query", help='e.g. "Rannischer Platz Halle"')

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


def _find_stop(query: str) -> None:
    from home_dashboard.app import create_http_client
    from home_dashboard.widgets.departures.insa_hafas import InsaHafasProvider

    with create_http_client() as http:
        matches = InsaHafasProvider(http).search_stops(query)
    if not matches:
        print("Keine Haltestelle gefunden.")
    for match in matches:
        print(f"{match.id:>10}  {match.name}")


if __name__ == "__main__":
    main()
