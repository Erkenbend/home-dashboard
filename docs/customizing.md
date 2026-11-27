# Make it yours

The dashboard was built for one household in Halle (Saale), Germany: German UI, trams from the
INSA network (Saxony-Anhalt), a shared Google Calendar and an old Samsung tablet. Most of that is
configuration; the rest sits behind small interfaces, so swapping a data source does not touch the
logic or the templates.

| You want to… | Effort | Where |
|---|---|---|
| use your own stops, people and location (Saxony-Anhalt) | config only | [`config.yaml`](#1-configuration) |
| use another iCal calendar (Nextcloud, iCloud, Outlook, …) | config only | [`calendar.ical_url`](#3-calendar) |
| watch your own services (green / yellow / red) | config only | [`status.services`](#5-services-status) |
| show trams/buses in another city or country | new provider class | [transit provider](#2-switch-the-transit-provider) |
| translate the UI | edit texts in place | [language](#6-language-and-look) |
| add a widget | source + service + template | [new widgets](#7-add-a-widget) |

## 1. Configuration

Copy [`config.example.yaml`](../config.example.yaml) to `config.yaml` (gitignored) and adapt it;
`uv run home-dashboard check-config` validates it. The essentials:

- **`home.lat` / `home.lon`**: location for the weather.
- **`departures.stops`**: one entry per stop you walk to.
  - `id`: look it up with `uv run home-dashboard find-stop "<stop name> <city>"`.
  - `walk_minutes`: your walking time. Trams you cannot catch any more are hidden, and
    "los in X min" counts down to the moment you have to leave.
  - `via` (optional): the id of a stop the tram must pass next; this is how "towards the city
    centre" is expressed. `direction` (optional) is a label shown next to the stop name instead of
    each tram's destination.
  - `lines` (optional): only these lines. `departures.products` selects trams, buses, trains.
- **`birthdays`** (optional): a second iCal feed (`birthdays.ical_url`), e.g. a calendar of yearly
  birthdays and anniversaries, listed small below the calendar for the next `birthdays.days`
  (14). `birthdays.enabled: false` hides it, `birthdays.title` names it. Each event gets an icon
  (birthday, anniversary, other), the person, the contact it is stored with in parentheses (a
  child's birthday stored with a parent; `birthdays.ignore_contacts` hides e.g. a contact that only
  collects birthdays) and "wird 4" / "11 Jahre" if the year is known. This is read from the events'
  descriptions as a contacts sync writes them ("Heute hat … Geburtstag!", "Besonderes Ereignis: …
  (aus …)", "Jahr: …"), with the title as fallback; for another format adapt the `RULES` in
  [`widgets/birthdays/parsing.py`](../src/home_dashboard/widgets/birthdays/parsing.py).
- **`calendar.people`**: a name, a colour and title keywords per person. An event titled
  "Alice: Zahnarzt" is shown as "Zahnarzt (Alice)" in Alice's colour. Events matching
  `calendar.everyone.match`, or no person at all, get the "Alle" colour.
- **`timezone`**, refresh and fetch intervals: see the comments in the example.

The INSA provider covers all of Saxony-Anhalt (Halle, Magdeburg, Dessau, regional trains and
buses), so within that region a new config is all you need.

## 2. Switch the transit provider

Everything transit-specific lives in one class implementing `DepartureProvider`
([`widgets/departures/provider.py`](../src/home_dashboard/widgets/departures/provider.py)):

```python
class DepartureProvider(Protocol):
    def departures(
        self,
        stop_id: str,
        start: datetime,
        duration_minutes: int,
        via_id: str | None = None,
        products: list[Product] | None = None,
    ) -> list[Departure]: ...

    def search_stops(self, query: str) -> list[StopMatch]: ...
```

A `Departure` holds trip id, line, product (`tram`, `bus`, …), destination, planned and realtime
departure (timezone-aware) and a cancelled flag. Reachability, line filters, duplicates, the
countdowns and the "Stand: HH:MM" fallback are handled by the service, not the provider. Raise
`ProviderError` when the upstream data is unusable.

The smallest working provider is `FakeDepartures` in
[`scripts/screenshot.py`](../scripts/screenshot.py); the real one is
[`insa_hafas.py`](../src/home_dashboard/widgets/departures/insa_hafas.py).

Steps:

1. **Pick a data source** for your region. Some starting points:
   - Other **HAFAS** instances: many German and European operators run the same backend as INSA, but
     each one needs its own request envelope (`auth`, `client`, `ver`). The profiles of
     [hafas-client](https://github.com/public-transport/hafas-client) list them. Often it is enough to
     pass a different `endpoint` and envelope to a copy of `InsaHafasProvider`.
   - **EFA** (e.g. several networks in Bavaria and North Rhine-Westphalia), **TRIAS**, or a national
     open-data API.
   - [**Transitous**](https://transitous.org/): open, community-run routing (MOTIS) across many
     countries without an API key; realtime only where the operator publishes it (for Halle it
     did not, see [ADR 0003](decisions/0003-transit-data-source.md)).
   - **GTFS + GTFS-Realtime** feeds of your operator, if published.
2. **Spike it**: a throwaway script (like [`spikes/transit/`](../spikes/transit/)) that fetches a
   station board for your stop. Check realtime data and delays, cancellations and how to express a
   direction. Save the real responses to `tests/fixtures/<provider>/`.
3. **Implement** `widgets/departures/<provider>.py` with a class taking an `httpx.Client`.
   - `via_id`: keep only trips that pass that stop next. If your API cannot do that, ignore it
     and use `lines` in the config instead; the dashboard works fine without `via`.
   - `products`: filter upstream if the API can, the service filters again anyway.
   - `search_stops`: used by `home-dashboard find-stop`; return `StopMatch(id, name)` with the id
     format your `departures` expects.
4. **Wire it in**: replace `InsaHafasProvider(http)` in `create_app`
   ([`app.py`](../src/home_dashboard/app.py)) and in `_find_stop`
   ([`cli.py`](../src/home_dashboard/cli.py)). If you want to keep several providers, add a
   `departures.provider` setting to `DeparturesConfig` in
   [`config.py`](../src/home_dashboard/config.py) and choose there.
5. **Test** like [`tests/test_departures.py`](../tests/test_departures.py): a fake endpoint
   ([`tests/hafas_fake.py`](../tests/hafas_fake.py), via `respx`) answers with your recorded
   responses, a `FixedClock` sets the time, and the assertions read the rendered HTML. Add a
   `@pytest.mark.live` smoke test against the real API (`uv run pytest -m live`) to notice format
   changes early.

## 3. Calendar

`calendar.ical_url` accepts any iCal (`.ics`) feed, not only Google: Nextcloud, iCloud (public
calendar), Outlook (published calendar), a file served from your NAS. Recurring events, exceptions
and all-day events are expanded by `recurring-ical-events`. The URL usually grants read access to
anyone who has it, so it lives only in the gitignored `config.yaml` and is never logged.

For a backend without iCal (e.g. the Google Calendar API with a service account), implement
`CalendarSource.events(start, end)`
([`widgets/calendar/source.py`](../src/home_dashboard/widgets/calendar/source.py)) and pass it in
`create_app`. The birthdays widget reads its feed through the same interface (`birthdays_source`).

## 4. Weather

[Open-Meteo](https://open-meteo.com/) works worldwide without an API key (free for non-commercial
use): set `home.lat` / `home.lon`, or `weather.enabled: false` to hide the widget. Another service
only needs a `WeatherSource`
([`widgets/weather/source.py`](../src/home_dashboard/widgets/weather/source.py)) that maps its
conditions to WMO weather codes, which drive the texts and icons.

## 5. Services status

The header shows a bubble per entry of `status.services`: a short `name` and a health check `url`.
The Pi sends a `GET` to each URL at most every `status.check_seconds` (default 60 s) and expects a
2xx answer within `status.timeout_seconds`; redirects count as failures, so configure the final URL.
Green: the last check succeeded, yellow: it failed, red: two or more failed in a row.

- The dashboard runs in Docker, where `localhost` is the container. Services on the Pi itself are
  `http://host.docker.internal:<port>/…` (mapped in `compose.yaml`); they must listen on more than
  `127.0.0.1`. Other devices are reached by host name or IP as usual.
- Good URLs are cheap and say "working", not just "listening": an `/health` or `/api/` endpoint, a
  login page. Without one, the start page will do.
- If not all bubbles fit next to the date, healthy services are hidden first.
- Another kind of check (TCP port, ping, a JSON field) only needs a `HealthCheck`
  ([`widgets/status/source.py`](../src/home_dashboard/widgets/status/source.py)): `check(url)`
  returns or raises `Unhealthy`.

## 6. Language and look

There is no i18n layer; the German texts sit where they are used:

- templates in [`templates/`](../src/home_dashboard/templates/) (headings, "los in", "fällt aus", "Stand:", "echt", "gefühlt", offline notice)
- [`formatting.py`](../src/home_dashboard/formatting.py) (weekday and month names, date formats, "Heute", "Morgen")
- [`widgets/calendar/service.py`](../src/home_dashboard/widgets/calendar/service.py) ("ganztägig", "Tag 1/3")
- [`widgets/weather/service.py`](../src/home_dashboard/widgets/weather/service.py) (weather descriptions, UV categories, "jetzt", "16 Uhr")
- [`widgets/status/service.py`](../src/home_dashboard/widgets/status/service.py) (the bubbles' tooltips)
- [`widgets/birthdays/`](../src/home_dashboard/widgets/birthdays/) ("wird 4", "11 Jahre"; the parsing rules match German event texts)
- [`cli.py`](../src/home_dashboard/cli.py) (`check-config` and `find-stop` output)

The tests assert on the rendered German texts, so `uv run pytest` shows what to update alongside.

Colours, sizes and the layout are plain CSS in
[`static/style.css`](../src/home_dashboard/static/style.css) (dark theme, sizes in `rem`, one root
font size per display size). Widgets never scroll: [`static/fit.js`](../src/home_dashboard/static/fit.js)
hides the least important rows until everything fits (see [architecture](architecture.md)), and
`tests/test_layout.py` checks this for several viewports in headless Chromium.

## 7. Add a widget

Each widget follows the same pattern, e.g. [`widgets/weather/`](../src/home_dashboard/widgets/weather/):

1. `source.py`: a `Protocol` for the external system plus plain dataclasses, and one concrete source.
2. `service.py`: the logic, using the source, the injected `Clock` and the shared `TtlCache`
   (keeps the last good value, so an outage shows "Stand: HH:MM" instead of an empty widget).
3. A fragment template in `templates/widgets/`, a route `/widgets/<name>` and a polling container
   in `index.html` (`hx-get` + `hx-trigger="every …s"`).
4. A config section in `config.py` and `config.example.yaml`.
5. Behaviour tests with recorded responses and a `FixedClock`, plus a layout test if it changes the page.

## 8. Hardware

Any always-on machine that runs Docker can be the server (see [setup](setup.md)), and any device
with a browser can be the display ([tablet setup](tablet.md)). Several displays can share one server;
upstream APIs are cached on the server, so they are not asked more often.
