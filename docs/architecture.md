# Architecture

## Overview

```
┌──────────────────────┐   HTTP :3274   ┌───────────────────────────────────────┐
│ Android tablet       │ ─────────────▶ │ Raspberry Pi 3b (Docker Compose)      │
│ kiosk browser        │  HTML pages +  │  FastAPI app                          │
│ (HTMX polls widgets) │  fragments     │   ├─ departures widget ──▶ transit API│
└──────────────────────┘                │   └─ calendar widget  ──▶ iCal feed   │
                                        │  in-memory TTL cache per source       │
                                        └───────────────────────────────────────┘
```

- **Server-side rendering**: FastAPI + Jinja2 render complete HTML. The browser only needs basic HTML/CSS.
- **HTMX** (1.9.x, vendored into `static/`) re-fetches each widget's HTML fragment periodically
  (`hx-get` + `hx-trigger="every 30s"`). No custom ES6+ JavaScript, no frontend build.
- **CSS**: plain CSS, Flexbox (no Grid) for compatibility with old Android WebViews. Dark theme, large type.

## Components

```
src/home_dashboard/
  app.py            create_app(config, clock, ...) -> FastAPI   (composition root)
  cli.py            `home-dashboard serve | find-stop`
  config.py         pydantic models, loads and validates config.yaml
  clock.py          Clock protocol (system clock in prod, fixed clock in tests)
  cache.py          TTL cache that keeps the last good value on upstream errors
  widgets/
    departures/
      provider.py   DepartureProvider protocol + Departure model
      insa_hafas.py concrete provider (INSA HAFAS, see ADR 0003)
      service.py    reachability + filter logic
      templates/
    calendar/
      source.py     CalendarSource protocol + Event model
      ical_source.py
      service.py    day grouping, person/colour matching
      templates/
  formatting.py     German date/time formatting (no system locale needed)
  templates/base.html, index.html, widgets/clock.html
  static/style.css, htmx.min.js
```

Each widget follows the same pattern: **source interface → service (pure logic) → fragment template**.
External systems are only reached through the source interface, so a source can be swapped
(e.g. iCal → Calendar API) without touching service or template.

## Routes

| Route | Content |
|---|---|
| `GET /` | Full page: layout, clock, widget containers |
| `GET /widgets/departures` | Departures fragment |
| `GET /widgets/calendar` | Calendar fragment |
| `GET /healthz` | Health check (used by deploy script) |

## Caching and refresh

| Source | Server cache TTL | Browser refresh |
|---|---|---|
| Departures (per stop) | ~30–60 s | 30 s |
| Calendar | ~10 min | 5 min |

On upstream errors the cache serves the last good value; the fragment shows "Stand: HH:MM".

## Configuration

`config.yaml` (gitignored; documented template in `config.example.yaml`), mounted read-only into the container:

```yaml
home:
  address: "…"
  lat: 51.48
  lon: 11.97
departures:
  max_per_stop: 5
  products: [tram]   # HAFAS product filter, default: trams only
  stops:
    - name: "Rannischer Platz"
      id: "…"              # HAFAS lid, look up with `find-stop`
      walk_minutes: 5
      via: "…"             # optional: lid of a stop the trip must pass (direction), e.g. Marktplatz
      lines: ["1", "95"]   # optional
    - name: "Franckeplatz"
      id: "…"
      walk_minutes: 12
      via: "…"             # e.g. Hauptbahnhof
calendar:
  ical_url: "https://calendar.google.com/calendar/ical/…/basic.ics"
  days: 7
  people:
    - name: "Anna"
      color: "#e07a5f"
      match: ["Anna", "A:"]
```

## Testing strategy

- Behaviour-level tests against the real ASGI app (`create_app` with test config).
- Outbound HTTP is intercepted with `respx` and answered with **recorded real responses** from `tests/fixtures/`.
- Time is controlled through the injected `Clock`.
- Assertions are made on the rendered HTML (what the user would see).
- Optional live smoke tests (`@pytest.mark.live`, skipped by default) detect upstream format changes.
- Tests run only in WSL: `uv run pytest`.

## Deployment

Development and builds happen in WSL; the Pi only runs the container.

`scripts/deploy.sh [user@host]` (default `pi@192.168.0.10`):

1. Check the Pi: `docker compose` available, `~/home-dashboard/config.yaml` present
2. `docker buildx build --platform linux/arm64 -t home-dashboard:<git-sha> --load .`
   (Docker Desktop emulates arm64 out of the box; plain Docker needs `tonistiigi/binfmt` once)
3. `docker save … | gzip | ssh <host> 'gunzip | docker load'` (no registry; the Pi never builds)
4. Copy `compose.yaml` to `~/home-dashboard/`, `docker compose up -d` with `TAG=<git-sha>`,
   then poll `http://<host>:3274/healthz`

Container: `restart: unless-stopped`, `TZ=Europe/Berlin`, port `3274:3274`, Docker `HEALTHCHECK` on `/healthz`.
