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
