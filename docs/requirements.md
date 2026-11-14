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
- Only **trams** are shown (buses are ignored). The transport modes are configurable
  (`departures.products`, default `[tram]`) in case this changes.
- Optional per-stop filters for lines and direction. The direction is expressed as a `via` stop the trip must
  pass (e.g. Rannischer Platz via Marktplatz = towards the city centre; Franckeplatz via Hauptbahnhof = towards
  the main station).
- Optional per-stop direction label (e.g. "Markt", "Hauptbahnhof"), shown next to the stop name. Departures
  of such a stop show only the line number instead of each trip's destination.
- Cancelled trips are visibly marked.
- Data source: live public transport data covering HAVAG (Hallesche Verkehrs-AG) trams and buses
  within the MDV network. See [ADR 0003](decisions/0003-transit-data-source.md).

### FR-2 Calendar widget

- Shows events of a shared Google Calendar for the upcoming 7 days (including today).
- Pleasant, glanceable format: grouped by day ("Heute", "Morgen", "Mi, 11.11."), all-day events first,
  past events of today de-emphasised.
- Recurring events, exceptions, multi-day and all-day events are handled correctly (timezone Europe/Berlin).
- The person(s) concerned can be derived from the event title. A configurable mapping
  (person → colour → title keywords, case-insensitive whole words) colours events accordingly.
- Some events concern **everyone**: recognized by configurable keywords (e.g. "Familie") or by the absence
  of any person keyword. They get their own colour and the label "Alle".
- Keywords at the start of a title are prefixes ("A - Zahnarzt", "Anna & Ben: Kino") and are not shown;
  instead the names of the people concerned follow the title in parentheses, de-emphasised
  ("Zahnarzt (Anna)"). Events for everyone get no names.
- The start time stands out (larger) from the end time.
- **Recurring events** (series, including moved occurrences) are visually distinguished from **single
  events**: single events stand out, recurring ones are de-emphasised and marked with a repeat icon.
- Access initially via the calendar's secret iCal address; a switch to the Google Calendar API
  (service account) must remain possible. See [ADR 0002](decisions/0002-calendar-via-ical.md).

### FR-3 General display

- Current time and date.
- The layout adapts to the display (further displays may be added): texts never overlap, there are no
  scrollbars, and each widget shows as many rows as fit. `departures.max_per_stop` and `calendar.days`
  are upper limits only.
- Widgets refresh automatically; the page never needs manual interaction.
- When a data source is unavailable, the last known data is shown with a "Stand: HH:MM" hint instead of
  an empty widget.
- When the tablet cannot reach the server, a visible "Keine Verbindung seit HH:MM" notice replaces the date
  and the frozen widgets are dimmed; both clear by themselves once the server answers again.

### FR-4 Weather widget

- Shown below the departures (same column): the weather matters when leaving the house. The departures
  give up rows for it.
- One row, nothing more detailed: the current temperature for the home location (`home.lat` /
  `home.lon`), then the weather (icon) now, in 1 hour and in 2 hours. "In n hours" is the forecast for the
  full hour nearest to now + n hours. The German description ("Leicht bewölkt") is the icon's title.
- Day and night icons (sun / moon) according to daylight at that time.
- Data source: Open-Meteo, no API key. See [ADR 0004](decisions/0004-weather-via-open-meteo.md).
- Without coordinates (or with `weather.enabled: false`) the widget is not shown.

### Future widget ideas (not in scope yet)

- Photo of the day (e.g. Wikimedia Commons Picture of the Day, or own photos).
- Further ideas welcome; widgets must be addable without touching existing ones.

## Non-functional requirements

| Topic | Requirement |
|---|---|
| UI language | German |
| Code / docs / commits | English |
| Display | Samsung Galaxy Tab A 10.1 (2016, SM-T580), Android 8.1, Fully Kiosk Browser (Chrome WebView), landscape, about 1280×800 CSS px, readable from 2–3 m. Setup: README |
| Browser compatibility | Conservative: server-side rendering, minimal JavaScript, no frontend build step |
| Server hardware | Raspberry Pi 3b (1 GB RAM, arm64, headless, no desktop environment) |
| Network / security | Home network only, no authentication, no exposure to the internet |
| Secrets | The secret iCal URL lives only in the gitignored `config.yaml` (WSL and Pi), never in git |
| Robustness | Survives reboots (auto start), API outages and Wi-Fi interruptions without manual intervention |
| API usage | External APIs are cached server-side; multiple displays must not multiply external requests |
| Development | Only in WSL on the developer machine (tests, builds). The Pi only runs the deployed container |
| Deployment | One deploy script updates the Pi |
| Testability | Behaviour-level integration tests with recorded API responses and an injectable clock; layout tests in headless Chromium (Playwright) |
| Server port | 3274 (T9 for "DASH") |

## Hardware available

- Raspberry Pi 3b, 64-bit OS
- Several old Android tablets (in use: Samsung Galaxy Tab A 10.1 2016, Android 8.1)
