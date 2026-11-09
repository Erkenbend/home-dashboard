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
