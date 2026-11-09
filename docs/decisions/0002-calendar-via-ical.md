# ADR 0002: Read the Google Calendar via its secret iCal address

- Status: accepted
- Date: 2026-11-09

## Context

Events of a shared Google Calendar must be shown read-only. Options are the calendar's secret iCal address,
the Google Calendar API with a service account, or the Calendar API with OAuth for a dedicated Google account.

## Decision

Start with the **secret iCal address** ("Privatadresse im iCal-Format" in the calendar settings).
It is stored only in `config.yaml` on the Pi. Parsing uses `icalendar` + `recurring-ical-events`
(recurrence rules, exceptions, timezones).

The calendar is accessed exclusively through the `CalendarSource` interface, so an implementation based on
the Calendar API (service account) can be added later without changing service logic or templates.

## Consequences

- No Google Cloud project, no OAuth, no token expiry.
- Google refreshes the iCal feed with a delay (minutes up to a few hours); acceptable for a weekly overview.
- Anyone with the URL can read the calendar: the URL is treated as a secret and never committed.
