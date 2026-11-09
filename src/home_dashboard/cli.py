"""Command line entry point: `home-dashboard serve` (more helpers follow, e.g. find-stop)."""

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

    args = parser.parse_args(argv)
    if args.command == "serve":
        uvicorn.run(
            "home_dashboard.app:create_app_from_env",
            factory=True,
            host=args.host,
            port=args.port,
            reload=args.reload,
        )


if __name__ == "__main__":
    main()
