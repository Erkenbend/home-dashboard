# ADR 0004: Weather data from Open-Meteo

- Status: accepted
- Date: 2026-11-14
- Amended: 2026-11-14, the widget only shows now, +1 h and +2 h: the request asks for `current` and
  `hourly` only (no `daily`, apparent temperature or precipitation probability)

## Context

The dashboard shows the current weather and a short forecast for home (FR-4). The source must be free for
private use, work without registration or API key, and offer current conditions, hourly and daily values
for a coordinate. Candidates:

- **Open-Meteo** (`api.open-meteo.com/v1/forecast`): no key, free for non-commercial use, combines national
  weather models (for Germany DWD ICON-D2/ICON-EU via `best_match`), WMO weather codes, current + hourly +
  daily values in one request, timestamps as unix time.
- **Bright Sky** (DWD open data as JSON): no key, DWD MOSMIX forecasts, own icon/condition names, no daily
  aggregates (min/max would have to be computed).
- **DWD open data directly** (MOSMIX KML): no key, but large files and heavy parsing for a Pi 3b.

## Decision

Use **Open-Meteo**, one request per fetch with `current`, `hourly` (2 days) and `daily` (today, tomorrow),
`timezone` set to the configured timezone and `timeformat=unixtime` (unambiguous around DST changes).
The location is `home.lat` / `home.lon`.

The widget reaches the API only through the `WeatherSource` interface. The forecast model uses WMO weather
codes, which other sources can be mapped to, so a switch (e.g. to Bright Sky) only needs a new source.

## Consequences

- No account, no secret in the config.
- Open-Meteo updates its models hourly, so fetching every 15 minutes is plenty and stays far below the
  free limit (10,000 requests per day).
- Conditions are shown with own inline SVG icons per WMO code group (no icon font, no emoji: the tablet's
  WebView and the test browser render them differently).
