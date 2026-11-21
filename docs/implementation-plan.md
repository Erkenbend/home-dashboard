# Implementation plan

Each step ends with a commit on `main`. See [requirements](requirements.md) and [architecture](architecture.md).

| # | Step | Content | Status |
|---|---|---|---|
| 0 | Documentation | Requirements, architecture, ADRs 0001–0003, README | done |
| 1 | Transit API spike | Throwaway script (outside `src/`) evaluating the candidates of ADR 0003 for a Halle stop; record real responses as test fixtures; finalize ADR 0003 | done: INSA HAFAS chosen |
| 2 | Skeleton | `pyproject.toml` (uv), FastAPI app with base layout + clock + `/healthz`, config loading, `config.example.yaml`, Dockerfile (python:3.12-slim, arm64), `compose.yaml`, `scripts/deploy.sh`; deploy once to the Pi to validate the pipeline early | done (deployed to Pi) |
| 3 | Departures widget | Provider from the spike, reachability/filter service, fragment template, behaviour tests, `find-stop` CLI | done |
| 4 | Calendar widget | iCal source, day grouping, person colours incl. "Alle", single vs. recurring events, fragment template, behaviour tests | done |
| 5 | Tablet setup + polish | Kiosk browser setup ([tablet setup](tablet.md): start URL, screen always on, reload on connection loss), layout tuning on the real device, visible error states | in progress: kiosk setup documented (Galaxy Tab A 2016, Fully Kiosk Browser), offline indicator done; open: layout tuning on the real device |
| 6 | Weather widget | ADR 0004 (Open-Meteo), weather source + service, fragment below the departures, behaviour and layout tests | done |
| 7 | Services status widget | ADR 0005, health check source + service (consecutive failures), bubbles in the header, behaviour and layout tests | in progress |

## Later

- Photo of the day (Wikimedia Commons POTD or own photos)
- Disruption notices ("Störungen") in the departures widget from HAFAS `himL`
- Transitous as schedule-only fallback provider, if INSA HAFAS becomes unavailable
- Calendar via Google Calendar API (service account), if the iCal delay becomes annoying

## Verification per milestone

1. `uv run pytest` and `uv run ruff check` green in WSL.
2. `uv run home-dashboard serve --reload` (port 3274) with a local `config.yaml` shows real
   departures and real events.
3. After `scripts/deploy.sh <pi-host>`, `http://<pi-host>:3274/healthz` returns 200 and the tablet shows the
   dashboard; check readability from 2–3 m, auto refresh over several hours and behaviour on Wi-Fi loss.
