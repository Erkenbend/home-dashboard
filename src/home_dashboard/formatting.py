"""German date/time formatting without relying on system locales (slim containers have none)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
WEEKDAYS_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]  # fmt: skip


def format_time(value: datetime) -> str:
    return value.strftime("%H:%M")


def format_long_date(value: date) -> str:
    """e.g. 'Montag, 9. November 2026'."""
    return f"{WEEKDAYS[value.weekday()]}, {value.day}. {MONTHS[value.month - 1]} {value.year}"


def format_short_date(value: date) -> str:
    """e.g. 'Mi, 11.11.'."""
    return f"{WEEKDAYS_SHORT[value.weekday()]}, {value.day:02d}.{value.month:02d}."


def format_day_label(day: date, today: date) -> str:
    """'Heute', 'Morgen', otherwise e.g. 'Mi, 11.11.'."""
    if day == today:
        return "Heute"
    if day == today + timedelta(days=1):
        return "Morgen"
    return format_short_date(day)
