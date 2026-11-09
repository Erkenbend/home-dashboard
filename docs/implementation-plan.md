# Implementation plan

Each step ends with a commit on `main`. See [requirements](requirements.md) and [architecture](architecture.md).

| # | Step | Content | Status |
|---|---|---|---|
| 0 | Documentation | Requirements, architecture, ADRs 0001–0003, README | done |
| 1 | Transit API spike | Throwaway script (outside `src/`) evaluating the candidates of ADR 0003 for a Halle stop; record real responses as test fixtures; finalize ADR 0003 | open |
| 2 | Skeleton | `pyproject.toml` (uv), FastAPI app with base layout + clock + `/healthz`, config loading, `config.example.yaml`, Dockerfile (python:3.12-slim, arm64), `compose.yaml`, `scripts/deploy.sh`; deploy once to the Pi to validate the pipeline early | open |
| 3 | Departures widget | Provider from the spike, reachability/filter service, fragment template, behaviour tests, `find-stop` CLI | open |
| 4 | Calendar widget | iCal source, day grouping, person colours, fragment template, behaviour tests | open |
| 5 | Tablet setup + polish | README section on kiosk browser setup (start URL, screen always on, reload on connection loss), layout tuning on the real device, visible error states | open |

## Later

- Weather widget (Open-Meteo, no API key)
- Photo of the day (Wikimedia Commons POTD or own photos)
- Calendar via Google Calendar API (service account), if the iCal delay becomes annoying

## Verification per milestone

1. `uv run pytest` and `uv run ruff check` green in WSL.
2. `uv run uvicorn home_dashboard.app:app --reload --port 3274` with a local `config.yaml` shows real
   departures and real events.
3. After `scripts/deploy.sh <pi-host>`, `http://<pi-host>:3274/healthz` returns 200 and the tablet shows the
   dashboard; check readability from 2–3 m, auto refresh over several hours and behaviour on Wi-Fi loss.
