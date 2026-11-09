# home-dashboard

Personal wall dashboard for home (Halle/Saale): an old Android tablet in kiosk mode shows a web page served
by a Raspberry Pi in the home network.

Initial widgets:

- **Abfahrten**: live departures of nearby trams/buses that are still reachable when leaving now
- **Kalender**: events of the shared Google Calendar for the coming week, coloured by person

## Documentation

- [Requirements](docs/requirements.md)
- [Architecture](docs/architecture.md)
- [Implementation plan](docs/implementation-plan.md)
- Decisions: [0001 Stack and operations](docs/decisions/0001-stack-and-operations.md),
  [0002 Calendar via iCal](docs/decisions/0002-calendar-via-ical.md),
  [0003 Transit data source](docs/decisions/0003-transit-data-source.md)

## Quick facts

- Stack: Python 3.12, FastAPI, Jinja2, HTMX, Docker Compose
- Port: **3274** (T9 for "DASH")
- Development and tests in WSL only; the Pi is updated via `scripts/deploy.sh`

## Development (WSL)

```sh
uv sync                                   # install dependencies (Python 3.12 is fetched by uv)
cp config.example.yaml config.yaml        # local config, gitignored
uv run pytest                             # behaviour tests (live tests: uv run pytest -m live)
uv run ruff check && uv run ruff format --check
uv run home-dashboard serve --reload      # http://localhost:3274/
uv run home-dashboard find-stop "Franckeplatz Halle"   # stop ids for config.yaml
uv run home-dashboard check-config        # validate config.yaml
```

## Deployment (Raspberry Pi)

One-time setup on the Pi (`pi@192.168.0.10`):

1. Install Docker and the compose plugin, add the user to the `docker` group
   (Debian trixie: `sudo apt install docker.io docker-compose && sudo usermod -aG docker $USER`, re-login).
2. SSH key login from WSL: `ssh-copy-id pi@192.168.0.10`.

Configuration: keep the real `config.yaml` (contains the secret iCal URL, gitignored, never commit it) in the
repo root in WSL. `scripts/deploy.sh` validates it (`uv run home-dashboard check-config`) and uploads it to
`~/home-dashboard/config.yaml` on the Pi. Without a local `config.yaml` the one on the Pi is kept.

Deploy (from WSL, Docker running):

```sh
scripts/deploy.sh                         # or: scripts/deploy.sh user@host
```

The script validates and uploads the config, cross-builds the arm64 image, ships it via SSH, recreates the
container with `docker compose` and waits for `http://<pi>:3274/healthz`.
After config-only changes simply run the script again.
