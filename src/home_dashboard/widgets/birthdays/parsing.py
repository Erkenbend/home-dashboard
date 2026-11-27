"""What an event of the birthdays calendar is about: kind, person, contact and year.

The rules are tuned to a calendar synced from the address book (Android contacts sync, German):

- a contact's birthday
    SUMMARY:     Geburtstag Max Muster
    DESCRIPTION: Heute hat Max Muster Geburtstag!\\nJahr: 1988      (or "Jahr: unbekannt")
- a special event stored with a contact, e.g. the birthday of a child stored with a parent
    SUMMARY:     Geburtstag Mia (Max Muster)
    DESCRIPTION: Besonderes Ereignis: Geburtstag Mia (aus Max Muster)\\nJahr: 2022
  or an anniversary ("Besonderes Ereignis: Anniversary (aus Max Muster)")

The description is unambiguous (the contact is marked with "aus"), the summary is not
("Geburtstag Mia (Tochter Lea)" may be a name with a note), so the description rules come first;
the summary rules are a fallback for events entered by hand or other calendars.

Another calendar format only needs other RULES (first match wins) and YEAR patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from home_dashboard.widgets.calendar.source import Event


class Kind(StrEnum):
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    OTHER = "other"


@dataclass(frozen=True)
class Rule:
    """A pattern on the event's summary or description.

    Named groups: `name` (who or what the event is about, required) and optionally `contact` (the
    address book entry it is stored with). Patterns are matched per line (re.MULTILINE).
    """

    field: str  # "summary" | "description"
    pattern: str
    kind: Kind


_SPECIAL = r"^Besonderes Ereignis: "
_CONTACT = r" \(aus (?P<contact>.+?)\)$"
_ANNIVERSARY = r"(?:Anniversary|Jahrestag|Hochzeitstag)"

RULES: list[Rule] = [
    Rule("description", r"^Heute hat (?P<name>.+?) Geburtstag!", Kind.BIRTHDAY),
    Rule("description", _SPECIAL + r"Geburtstag (?P<name>.+)" + _CONTACT, Kind.BIRTHDAY),
    # The anniversary of the contact itself (of a couple: stored with one of them)
    Rule("description", _SPECIAL + _ANNIVERSARY + r" \(aus (?P<name>.+?)\)$", Kind.ANNIVERSARY),
    Rule("description", _SPECIAL + r"(?P<name>.+)" + _CONTACT, Kind.OTHER),
    Rule("summary", r"^Geburtstag:? (?P<name>.+)$", Kind.BIRTHDAY),
    Rule("summary", r"^(?P<name>.+?):? Geburtstag$", Kind.BIRTHDAY),
    Rule("summary", rf"^(?P<name>.+?):? {_ANNIVERSARY}$", Kind.ANNIVERSARY),
    Rule("summary", rf"^{_ANNIVERSARY}:? (?P<name>.+)$", Kind.ANNIVERSARY),
]  # fmt: skip

# Year of birth / of the wedding; "Jahr: unbekannt" simply does not match
YEAR = [r"^Jahr: (?P<year>\d{4})$"]


@dataclass(frozen=True)
class Parsed:
    kind: Kind
    name: str
    contact: str | None
    year: int | None


_COMPILED = [(rule, re.compile(rule.pattern, re.MULTILINE)) for rule in RULES]
_YEAR = [re.compile(pattern, re.MULTILINE) for pattern in YEAR]


def parse(event: Event, ignore_contacts: list[str] | None = None) -> Parsed:
    """Kind, person and year of an event; unknown formats are shown by their title."""
    ignored = {contact.casefold() for contact in ignore_contacts or []}
    texts = {"summary": event.title, "description": event.description}
    kind, name, contact = Kind.OTHER, event.title, None
    for rule, pattern in _COMPILED:
        if match := pattern.search(texts[rule.field]):
            groups = match.groupdict()
            kind, name, contact = rule.kind, groups["name"].strip(), groups.get("contact")
            break
    if contact is not None and contact.strip().casefold() in ignored:
        contact = None
    year = next((int(m["year"]) for p in _YEAR if (m := p.search(event.description))), None)
    return Parsed(kind, name, contact.strip() if contact else None, year)
