# ADR 0003: Live departure data source for Halle (Saale)

- Status: **proposed** (to be decided by a spike, see implementation plan step 1)
- Date: 2026-11-09

## Context

Live departures (with delays and cancellations) for HAVAG trams and buses in Halle (Saale) are needed.
Research found no official, openly documented realtime API from HAVAG or the MDV
(Mitteldeutscher Verkehrsverbund). HAVAG offers live tracking only in its own apps.

## Candidates (in order of evaluation)

1. **INSA HAFAS** (Nahverkehr Sachsen-Anhalt). INSA covers all of Saxony-Anhalt and the MDV area.
   Community clients exist (`hafas-client` / `db-vendo-client` profile `insa`, npm `insa-hafas`).
   Unofficial; access via the HAFAS "mgate" JSON endpoint.
2. **Transitous** (community-run MOTIS instance with an open API based on DELFI data). No key needed.
   Unclear whether realtime data for HAVAG is included.
3. **MDV EFA** (Mentz EFA departure monitor, XML/JSON). Unofficial, endpoint to be verified.

## Evaluation criteria

- Covers HAVAG trams and buses, including realtime delays and cancellations
- No key or a free key; tolerable terms of use
- Stop search available (for the `find-stop` helper)
- Response stability (format, availability)

## Decision

Pending. The spike records the outcome here, including recorded sample responses used as test fixtures.
The application depends only on the `DepartureProvider` interface, so switching later stays cheap.
