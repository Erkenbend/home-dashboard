"""UI texts and date formats of one language, from `locales/<language>.toml` (see ADR 0006).

No system locales are used (slim containers have none): weekday and month names and the date
patterns come from the catalog as well.
"""

from __future__ import annotations

import os
import re
import string
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LANGUAGE = "de"
LANGUAGE_ENV = "HOME_DASHBOARD_LANGUAGE"
_LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]+)*$")

Text = str | list[str]


@dataclass(frozen=True)
class Translator:
    language: str
    texts: Mapping[str, Text]
    """Flat: section and key joined with dots, e.g. "departures.leave_in"."""

    def t(self, key: str, /, **values: object) -> str:
        """The text for `key` with its {placeholders} filled in."""
        return self.text(key).format(**values)

    def around(self, key: str, placeholder: str, /, **values: object) -> tuple[str, str]:
        """The text before and after `{placeholder}`, the other placeholders filled in.

        For texts with one emphasized part, e.g. "ab {time}" -> ("ab ", "").
        """
        before, _, after = self.text(key).partition("{" + placeholder + "}")
        return before.format(**values), after.format(**values)

    def time(self, value: datetime) -> str:
        return value.strftime("%H:%M")

    def hour(self, hour: int) -> str:
        """A full hour, e.g. '16 Uhr'."""
        return self.t("dates.hour", hour=hour)

    def long_date(self, value: date) -> str:
        """e.g. 'Montag, 9. November 2026'."""
        return self.t("dates.long_date", **self._date_fields(value))

    def short_date(self, value: date) -> str:
        """e.g. 'Mi, 11.11.'."""
        return self.t("dates.short_date", **self._date_fields(value))

    def day_label(self, day: date, today: date) -> str:
        """'Heute', 'Morgen', otherwise the short date."""
        if day == today:
            return self.t("dates.today")
        if day == today + timedelta(days=1):
            return self.t("dates.tomorrow")
        return self.short_date(day)

    def _date_fields(self, value: date) -> dict[str, object]:
        return {
            "weekday": self._list("dates.weekdays")[value.weekday()],
            "weekday_short": self._list("dates.weekdays_short")[value.weekday()],
            "day": value.day,
            "month": value.month,
            "month_name": self._list("dates.months")[value.month - 1],
            "year": value.year,
        }

    def text(self, key: str) -> str:
        """The raw text for `key`, placeholders not filled in."""
        value = self._lookup(key)
        if not isinstance(value, str):
            raise TypeError(f"text {key!r} of language {self.language!r} is not a string")
        return value

    def _list(self, key: str) -> list[str]:
        value = self._lookup(key)
        if not isinstance(value, list):
            raise TypeError(f"text {key!r} of language {self.language!r} is not a list")
        return value

    def _lookup(self, key: str) -> Text:
        try:
            return self.texts[key]
        except KeyError:
            raise KeyError(f"text {key!r} is missing in language {self.language!r}") from None


def available_languages() -> list[str]:
    return sorted(path.stem for path in LOCALES_DIR.glob("*.toml"))


def load_translator(language: str = DEFAULT_LANGUAGE) -> Translator:
    path = LOCALES_DIR / f"{language}.toml"
    if not _LANGUAGE_CODE.match(language) or not path.is_file():
        available = ", ".join(available_languages()) or "none"
        raise ValueError(f"language {language!r} is not available, available: {available}")
    with path.open("rb") as file:
        return Translator(language, flatten(tomllib.load(file)))


def language_from_env() -> str:
    return os.environ.get(LANGUAGE_ENV, DEFAULT_LANGUAGE)


def flatten(catalog: Mapping[str, object], prefix: str = "") -> dict[str, Text]:
    """{"a": {"b": "x"}} -> {"a.b": "x"}"""
    flat: dict[str, Text] = {}
    for key, value in catalog.items():
        if isinstance(value, Mapping):
            flat.update(flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value  # type: ignore[assignment]
    return flat


def placeholders(text: str) -> set[str]:
    """Names of the {placeholders} in a text, e.g. {"minutes"} for "los in {minutes} min"."""
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}
