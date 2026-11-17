"""CalendarSource reading a (Google) calendar via its secret iCal address, see ADR 0002."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
import icalendar
import recurring_ical_events

from home_dashboard.widgets.calendar.source import CalendarError, Event


class IcalCalendarSource:
    def __init__(self, http: httpx.Client, url: str, timezone: str) -> None:
        self._http = http
        self._url = url
        self._tz = ZoneInfo(timezone)

    def events(self, start: datetime, end: datetime) -> list[Event]:
        try:
            response = self._http.get(self._url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            # Never log the URL: it is a secret
            raise CalendarError(f"iCal download failed: {type(error).__name__}") from None
        try:
            calendar = icalendar.Calendar.from_ical(response.content)
            series_uids = {
                str(component.get("UID"))
                for component in calendar.walk("VEVENT")
                if "RRULE" in component or "RDATE" in component
            }
            occurrences = recurring_ical_events.of(calendar).between(start, end)
            return [self._to_event(component, series_uids) for component in occurrences]
        except (ValueError, KeyError) as error:
            raise CalendarError(f"invalid iCal data: {error!r}") from error

    def _to_event(self, component: icalendar.Event, series_uids: set[str]) -> Event:
        uid = str(component.get("UID", ""))
        return Event(
            uid=uid,
            title=str(component.get("SUMMARY", "")).strip() or "(ohne Titel)",
            start=self._normalize(component.decoded("DTSTART")),
            # recurring-ical-events sets DTEND on every occurrence: from DURATION, or by the RFC
            # 5545 defaults (a date lasts one day, a date-time is a point in time)
            end=self._normalize(component.decoded("DTEND")),
            recurring=uid in series_uids,
        )

    def _normalize(self, value: datetime | date) -> datetime | date:
        """Floating times are interpreted in the configured timezone, all others converted to it."""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=self._tz)
            return value.astimezone(self._tz)
        return value
