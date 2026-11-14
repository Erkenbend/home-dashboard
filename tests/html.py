"""Tiny helpers to read what the dashboard shows from rendered HTML."""

from __future__ import annotations

from html.parser import HTMLParser


class _DepartureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stops: dict[str, list[dict[str, str]]] = {}
        self._stop: str | None = None
        self._row: dict[str, str] | None = None
        self._cell: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if "data-stop" in attributes:
            self._stop = attributes["data-stop"] or ""
            self.stops[self._stop] = []
        elif tag == "tr" and "departure" in classes and self._stop is not None:
            self._row = {"cancelled": "cancelled" in classes}
            self.stops[self._stop].append(self._row)
        elif tag == "td" and self._row is not None:
            self._cell = classes[0] if classes else None

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self._cell = None
        elif tag == "tr":
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._row is not None and self._cell:
            text = " ".join((self._row.get(self._cell, "") + " " + data).split())
            self._row[self._cell] = text


def departures_by_stop(html: str) -> dict[str, list[dict[str, str]]]:
    """{stop name: [{line, direction, time, minutes, leave, status, cancelled}, ...]}"""
    parser = _DepartureParser()
    parser.feed(html)
    return parser.stops


class _StopDirectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.directions: dict[str, str | None] = {}
        self._stop: str | None = None
        self._in_direction = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "data-stop" in attributes:
            self._stop = attributes["data-stop"] or ""
            self.directions[self._stop] = None
        elif "stop-direction" in (attributes.get("class") or "").split() and self._stop:
            self._in_direction = True
            self.directions[self._stop] = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._in_direction = False

    def handle_data(self, data: str) -> None:
        if self._in_direction and self._stop is not None:
            self.directions[self._stop] = " ".join((self.directions[self._stop] + data).split())


def stop_directions(html: str) -> dict[str, str | None]:
    """{stop name: direction shown next to it, None if there is none}"""
    parser = _StopDirectionParser()
    parser.feed(html)
    return parser.directions


def lines(rows: list[dict[str, str]]) -> list[str]:
    return [row["line"] for row in rows]


class _CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.days: dict[str, list[dict]] = {}
        self._day: str | None = None
        self._event: dict | None = None
        self._fields: list[str | None] = []  # one per open span, text goes to all of them

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if "data-day" in attributes:
            self._day = attributes["data-day"] or ""
            self.days[self._day] = []
        elif tag == "li" and "event" in classes and self._day is not None:
            self._event = {
                "people": (attributes.get("data-people") or "").split(","),
                "recurring": "recurring" in classes,
                "past": "past" in classes,
                "everyone": "everyone" in classes,
                "time": "",
                "start": "",
                "title": "",
                "names": "",
            }
            self.days[self._day].append(self._event)
        elif tag == "span" and self._event is not None:
            fields = {
                "event-time": "time",
                "event-start": "start",
                "event-title": "title",
                "event-names": "names",
            }
            self._fields.append(next((fields[c] for c in classes if c in fields), None))

    def handle_endtag(self, tag: str) -> None:
        if tag == "span" and self._fields:
            self._fields.pop()
        elif tag == "li":
            self._event = None

    def handle_data(self, data: str) -> None:
        if self._event is None:
            return
        for field in filter(None, self._fields):
            self._event[field] += data  # whitespace is normalized at the end


def calendar_days(html: str) -> dict[str, list[dict]]:
    """{day label: [{title, names, time, start, people, recurring, past, everyone}, ...]}"""
    parser = _CalendarParser()
    parser.feed(html)
    for event in (event for events in parser.days.values() for event in events):
        for field in ("time", "start", "title", "names"):
            event[field] = " ".join(event[field].split())
    return parser.days


def titles(events: list[dict]) -> list[str]:
    return [event["title"] for event in events]


class _WeatherParser(HTMLParser):
    """Temperature now, the slots (now, in 1 h, in 2 h) with label, icon and its description."""

    def __init__(self) -> None:
        super().__init__()
        self.weather: dict = {"temperature": None, "slots": [], "notices": []}
        self._slot: dict | None = None
        self._field: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if "weather-slot" in classes:
            self._slot = {"label": "", "icon": None, "condition": ""}
            self.weather["slots"].append(self._slot)
        elif tag == "svg" and self._slot is not None:
            self._slot["icon"] = attributes.get("data-icon")
        elif tag == "title" and self._slot is not None:
            self._start("condition")
        elif "weather-slot-label" in classes:
            self._start("label")
        elif "weather-temperature" in classes:
            self._start("temperature")
        elif "notice" in classes:
            self._start("notice")

    def handle_endtag(self, tag: str) -> None:
        if self._field is not None and tag in ("span", "title", "p"):
            text = " ".join("".join(self._text).split())
            if self._field == "notice":
                self.weather["notices"].append(text)
            elif self._field == "temperature":
                self.weather["temperature"] = text
            else:
                self._slot[self._field] = text
            self._field = None
        elif tag == "span" and self._slot is not None:
            self._slot = None

    def handle_data(self, data: str) -> None:
        if self._field is not None:
            self._text.append(data)

    def _start(self, field: str) -> None:
        self._field, self._text = field, []


def weather(html: str) -> dict:
    """{temperature: "9°" or None, slots: [{label, icon, condition}], notices: [text]}"""
    parser = _WeatherParser()
    parser.feed(html)
    return parser.weather
