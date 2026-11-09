# Requirements

Personal wall-mounted dashboard for our home in Halle (Saale), Germany.

## Goal

A small screen (old Android tablet) hangs on the wall and permanently shows information that is useful
when leaving the house or planning the week. The dashboard is extensible: new widgets can be added over time.

## Functional requirements

### FR-1 Departures widget ("Which tram can I still catch?")

- The home location and a list of nearby stops of interest are configured.
- For each configured stop the walking time from home (in minutes) is configured manually.
- The widget shows live departures (including delays and cancellations) for the configured stops.
- Only departures that are **still reachable when leaving now** are shown:
  `departure_time (realtime if available) - now >= walking_time`.
- Each departure shows line, direction, minutes until departure and minutes until one has to leave home
  ("los in X min").
- Optional per-stop filters for lines and direction. The direction is expressed as a `via` stop the trip must
  pass (e.g. Rannischer Platz via Marktplatz = towards the city centre; Franckeplatz via Hauptbahnhof = towards
  the main station).
- Cancelled trips are visibly marked.
- Data source: live public transport data covering HAVAG (Hallesche Verkehrs-AG) trams and buses
  within the MDV network. See [ADR 0003](decisions/0003-transit-data-source.md).

### FR-2 Calendar widget

- Shows events of a shared Google Calendar for the upcoming 7 days (including today).
- Pleasant, glanceable format: grouped by day ("Heute", "Morgen", "Mi, 11.11."), all-day events first,
  past events of today de-emphasised.
- Recurring events, exceptions, multi-day and all-day events are handled correctly (timezone Europe/Berlin).
- The person(s) concerned can be derived from the event title. A configurable mapping
  (person → colour → title keywords) colours events accordingly. Events matching nobody get a neutral colour.
- Access initially via the calendar's secret iCal address; a switch to the Google Calendar API
  (service account) must remain possible. See [ADR 0002](decisions/0002-calendar-via-ical.md).

### FR-3 General display

- Current time and date.
- Widgets refresh automatically; the page never needs manual interaction.
- When a data source is unavailable, the last known data is shown with a "Stand: HH:MM" hint instead of
  an empty widget.

### Future widget ideas (not in scope yet)

- Current weather / forecast (e.g. Open-Meteo, no API key needed).
- Photo of the day (e.g. Wikimedia Commons Picture of the Day, or own photos).
- Further ideas welcome; widgets must be addable without touching existing ones.

## Non-functional requirements

| Topic | Requirement |
|---|---|
| UI language | German |
| Code / docs / commits | English |
| Display | Old Android tablet (version unknown), browser in kiosk mode, landscape, readable from 2–3 m |
| Browser compatibility | Conservative: server-side rendering, minimal JavaScript, no frontend build step |
| Server hardware | Raspberry Pi 3b (1 GB RAM, arm64, headless, no desktop environment) |
| Network / security | Home network only, no authentication, no exposure to the internet |
| Secrets | The secret iCal URL lives only in the local config on the Pi, never in git |
| Robustness | Survives reboots (auto start), API outages and Wi-Fi interruptions without manual intervention |
| API usage | External APIs are cached server-side; multiple displays must not multiply external requests |
| Development | Only in WSL on the developer machine (tests, builds). The Pi only runs the deployed container |
| Deployment | One deploy script updates the Pi |
| Testability | Behaviour-level integration tests with recorded API responses and an injectable clock |
| Server port | 3274 (T9 for "DASH") |

## Hardware available

- Raspberry Pi 3b, 64-bit OS
- Several old Android tablets
