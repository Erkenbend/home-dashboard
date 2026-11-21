# Architecture

## Overview

```
┌──────────────────────┐   HTTP :3274   ┌───────────────────────────────────────┐
│ Android tablet       │ ─────────────▶ │ Raspberry Pi 3b (Docker Compose)      │
│ kiosk browser        │  HTML pages +  │  FastAPI app                          │
│ (HTMX polls widgets) │  fragments     │   ├─ departures widget ──▶ transit API│
└──────────────────────┘                │   ├─ calendar widget  ──▶ iCal feed   │
                                        │   └─ weather widget   ──▶ Open-Meteo  │
                                        │  in-memory TTL cache per source       │
                                        └───────────────────────────────────────┘
```

- **Server-side rendering**: FastAPI + Jinja2 render complete HTML. The browser only needs basic HTML/CSS.
- **HTMX** (1.9.x, vendored into `static/`) re-fetches each widget's HTML fragment periodically
  (`hx-get` + `hx-trigger="every 30s"`). No custom ES6+ JavaScript, no frontend build.
- **Weather icons**: inline SVG macros (`templates/widgets/weather_icons.html`), one per WMO code group,
  sun or moon depending on daylight.
- **CSS**: plain CSS, Flexbox (no Grid) for compatibility with old Android WebViews. Dark theme, large type.
  Layout: departures and weather share the left half (departures two thirds of the height, weather
  one third with its content at the top, more if its tiles need it on small displays), calendar on the
  right half; in portrait everything is
  stacked and the column and the calendar share the height equally.
  All sizes are in `rem`; media queries set the root font size per display size (width or height,
  whichever is tighter), and switch to stacked widgets in portrait.
- **Fit to the display** (`static/fit.js`, plain ES5): widgets never scroll. The server renders up to the
  configured limits (`max_per_stop`, `days`), the script hides the least important rows until each
  widget fits, on load, resize and after every HTMX swap. Templates declare what may go via
  `data-fit-priority` (higher goes first, rows without it always stay) and `data-fit-group` (hidden when
  empty). Departures: the next one per stop stays, later ones go round-robin. Calendar: past events of
  today first, then from the end of the window.
- **Offline indicator** (`static/connection.js`, plain ES5): every HTMX poll reports the connection state.
  A network error or timeout (`htmx.config.timeout` 30 s, above the slowest widget request) sets
  `body.offline`: the date gives way to "Keine Verbindung seit HH:MM" (last clock time shown) and the
  widgets are dimmed, without changing the layout. Any server response clears it. HTTP error responses
  count as reachable; upstream failures are covered by "Stand: HH:MM".
- **Static asset URLs** carry a content hash (`static_url('style.css')` → `/static/style.css?v=<hash>`).
  StaticFiles sends no Cache-Control, so the kiosk WebView caches CSS/JS heuristically and would otherwise
  combine new HTML with stale assets after a deployment (e.g. the offline notice always visible).

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
    weather/
      source.py     WeatherSource protocol + Forecast model (WMO weather codes)
      open_meteo.py concrete source (Open-Meteo, see ADR 0004)
      service.py    upcoming hours, today/tomorrow, WMO code -> German text + icon
  formatting.py     German date/time formatting (no system locale needed)
  templates/base.html, index.html, widgets/clock.html, widgets/weather_icons.html
  static/style.css, fit.js, connection.js, htmx.min.js
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
| `GET /widgets/weather` | Weather fragment |
| `GET /healthz` | Health check (used by deploy script) |

## Caching and refresh

All intervals are configurable (defaults shown):

| What | Tablet polls the Pi (`refresh_seconds`) | Pi fetches upstream at most (`fetch_seconds`) |
|---|---|---|
| Clock (`display.clock_refresh_seconds`) | 15 s | – |
| Departures (per stop) | 30 s | 60 s (min. 15) |
| Calendar | 5 min | 10 min (min. 60 s) |
| Weather | 5 min | 15 min (min. 5 min) |
| Full page reload (`display.page_reload_hours`, 0 = off) | 6 h | – |

The cache treats an entry as expired slightly early (10 %, max. 5 s) so that a poll arriving a bit early
does not skip a whole fetch cycle.

On upstream errors the cache serves the last good value; the fragment shows "Stand: HH:MM".
Failed loads are also retried at most once per TTL, so a broken upstream (10 s HTTP timeout) does not
slow down every refresh. Reachability is recomputed on every request from the cached departures.

## Configuration

`config.yaml` (gitignored; documented template in `config.example.yaml`), maintained in WSL, uploaded by the
deploy script and mounted read-only into the container:

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
      id: "5258"           # numeric stop id, look up with `home-dashboard find-stop`
      walk_minutes: 5
      via: "5232"          # optional: stop the tram must pass later (direction), here Marktplatz
      direction: "Markt"   # optional: shown next to the stop name instead of each trip's destination
      lines: ["1", "95"]   # optional
    - name: "Franckeplatz"
      id: "5125"
      walk_minutes: 10
      via: "8010159"       # Hauptbahnhof
      direction: "Hauptbahnhof"
calendar:
  ical_url: "https://calendar.google.com/calendar/ical/…/basic.ics"
  days: 7
  people:
    - name: "Alice"
      color: "#e07a5f"
      match: ["Alice"]      # case-insensitive whole words ("Bob" does not match "Bobbycar")
  everyone:                 # keyword match OR no person recognized
    label: "Alle"
    color: "#c9b458"
    match: ["Familie", "Alle"]
weather:                    # location: home.lat / home.lon, shown only if both are set
  enabled: true
```

## Testing strategy

- Behaviour-level tests against the real ASGI app (`create_app` with test config).
- Outbound HTTP is intercepted with `respx` and answered with **recorded real responses** from `tests/fixtures/`.
- Time is controlled through the injected `Clock`.
- Assertions are made on the rendered HTML (what the user would see).
- Browser tests (`tests/browser.py` fixtures) run the page in headless Chromium against the same app:
  layout per viewport, and the offline indicator with a switchable network and fake timers.
- Optional live smoke tests (`@pytest.mark.live`, skipped by default) detect upstream format changes.
- Tests run only in WSL: `uv run pytest`.

## Deployment

Development and builds happen in WSL; the Pi only runs the container.

`scripts/deploy.sh [user@host]` (or `DEPLOY_HOST=user@host`):

1. If a local `config.yaml` exists: validate it (`home-dashboard check-config`); otherwise require
   `~/home-dashboard/config.yaml` on the Pi. Check `docker compose` on the Pi
2. `docker buildx build --platform linux/arm64 -t home-dashboard:<git-sha> --load .`
   (Docker Desktop emulates arm64 out of the box; plain Docker needs `tonistiigi/binfmt` once)
3. `docker save … | gzip | ssh <host> 'gunzip | docker load'` (no registry; the Pi never builds)
4. Upload the local `config.yaml` (mode 600) if present, copy `compose.yaml` to `~/home-dashboard/`,
   `docker compose up -d --force-recreate` with `TAG=<git-sha>`,
   then poll `http://<host>:3274/healthz`

Container: `restart: unless-stopped`, `TZ=Europe/Berlin`, port `3274:3274`, Docker `HEALTHCHECK` on `/healthz`.
