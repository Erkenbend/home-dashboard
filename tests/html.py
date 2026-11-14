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


def lines(rows: list[dict[str, str]]) -> list[str]:
    return [row["line"] for row in rows]


class _CalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.days: dict[str, list[dict]] = {}
        self._day: str | None = None
        self._event: dict | None = None
        self._field: str | None = None

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
                "title": "",
            }
            self.days[self._day].append(self._event)
        elif tag == "span" and self._event is not None:
            if "event-time" in classes:
                self._field = "time"
            elif "event-title" in classes:
                self._field = "title"

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._field = None
        elif tag == "li":
            self._event = None

    def handle_data(self, data: str) -> None:
        if self._event is not None and self._field:
            self._event[self._field] = " ".join((self._event[self._field] + data).split())


def calendar_days(html: str) -> dict[str, list[dict]]:
    """{day label: [{title, time, people, recurring, past, everyone}, ...]}"""
    parser = _CalendarParser()
    parser.feed(html)
    return parser.days


def titles(events: list[dict]) -> list[str]:
    return [event["title"] for event in events]


class _WeatherParser(HTMLParser):
    """Items (now, days, hours) with the text of their fields and their icon."""

    ITEMS = {"weather-now": "now", "weather-day": "days", "weather-hour": "hours"}
    FIELDS = {
        "weather-temperature": "temperature",
        "weather-condition": "condition",
        "weather-apparent": "apparent",
        "weather-day-label": "label",
        "weather-max": "max",
        "weather-min": "min",
        "hour-label": "label",
        "hour-temperature": "temperature",
        "hour-precipitation": "precipitation",
    }

    def __init__(self) -> None:
        super().__init__()
        self.weather: dict = {"now": None, "days": [], "hours": [], "notices": []}
        self._item: dict | None = None
        self._item_tag: str | None = None
        self._depth = 0
        self._field: str | None = None
        self._notice: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if self._item is not None and tag == self._item_tag:
            self._depth += 1
        kind = next((self.ITEMS[c] for c in classes if c in self.ITEMS), None)
        if kind is not None:
            self._item = {"classes": classes}
            self._item_tag, self._depth = tag, 1
            if kind == "now":
                self.weather["now"] = self._item
            else:
                self.weather[kind].append(self._item)
        elif self._item is not None:
            if tag == "svg" and "icon" not in self._item:
                self._item["icon"] = attributes.get("data-icon")
            field = next((self.FIELDS[c] for c in classes if c in self.FIELDS), None)
            if field:
                self._field = field
                self._item[field] = ""
        elif "notice" in classes:
            self._notice = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("span", "td"):
            self._field = None
        elif tag == "p" and self._notice is not None:
            self.weather["notices"].append(" ".join("".join(self._notice).split()))
            self._notice = None
        if self._item is not None and tag == self._item_tag:
            self._depth -= 1
            if self._depth == 0:
                self._item = None

    def handle_data(self, data: str) -> None:
        if self._item is not None and self._field:
            self._item[self._field] = " ".join((self._item[self._field] + data).split())
        elif self._notice is not None:
            self._notice.append(data)


def weather(html: str) -> dict:
    """{now: {temperature, condition, apparent, icon}, days: [{label, max, min, icon}],
    hours: [{label, temperature, precipitation, icon, classes}], notices: [text]}"""
    parser = _WeatherParser()
    parser.feed(html)
    return parser.weather
