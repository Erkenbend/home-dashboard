# ADR 0003: Live departure data source for Halle (Saale)

- Status: accepted
- Date: 2026-11-09

## Context

Live departures (with delays and cancellations) for HAVAG trams and buses in Halle (Saale) are needed.
Research found no official, openly documented realtime API from HAVAG or the MDV
(Mitteldeutscher Verkehrsverbund). HAVAG offers live tracking only in its own apps.

A spike (`spikes/transit/insa_hafas.py`) evaluated the candidates on 2026-11-09 ~21:35 with the example stops
Rannischer Platz (towards the city centre) and Franckeplatz (towards the main station).

## Results

| Candidate | Coverage HAVAG | Realtime | Access | Result |
|---|---|---|---|---|
| **INSA HAFAS** (`https://reiseauskunft.insa.de/bin/mgate.exe`) | trams + buses (incl. regional buses, e.g. OBS 380) | yes: `dTimeR` present, e.g. bus 380 +16 min, tram 1 −1 min | no key; unofficial, uses the client identification of the NASA app (as `hafas-client` profile `insa` does) | **chosen** |
| **Transitous** (MOTIS API, DELFI data) | trams + buses | **no**: `realTime=false` for all departures, the delayed bus 380 showed as on time | open, no key | fallback (schedule only) |
| **MDV EFA** | – | – | endpoint undocumented | not evaluated, INSA already meets all criteria |

## Decision

Use **INSA HAFAS** via direct JSON POSTs with `httpx` (no extra client library).

Implementation notes from the spike:

- **Requests**: `LocMatch` (stop search, used by the `find-stop` helper) and `StationBoard` (`type: DEP`).
  Request envelope: `auth {type: AID, aid: nasa-apps}`, `client {type: IPH, id: NASA, v: 4000200, name: nasaPROD}`,
  `ver: 1.44`, `lang: de`.
- **Stop IDs**: the `lid` string from `LocMatch` identifies the stop (also usable in config);
  `extId` is the short numeric ID (Rannischer Platz `5258`, Franckeplatz `5125`, matching DELFI `de:15002:5258`).
- **Direction filter**: `StationBoard` accepts `dirLoc` (a stop the trip must pass later). This is the reliable
  way to express "towards the city centre": e.g. Rannischer Platz via Marktplatz → only lines 1 and 95 northbound;
  Franckeplatz via Hauptbahnhof → buses 312/320/380, trams 7/94. The config therefore uses an optional **`via`
  stop** per configured stop instead of matching destination names.
- **Times**: `dTimeS` (scheduled) / `dTimeR` (realtime, missing if no prognosis) as `HHMMSS` relative to the
  journey's `date`; HAFAS prefixes a day offset for times after midnight (`ddHHMMSS`), the parser must handle it.
  `dTZOffset` gives the UTC offset in minutes.
- **Line name**: take the product via `stbStop.dProdX` (not `jny.prodX`), because a vehicle can change its line
  number during a trip (observed: line 94 continuing as line 7).
- **Duplicates**: a station board spans several stop points of the station (platforms `A`…`F`), so the same
  journey (`jid`) can appear twice within ~1 min (observed: line 94 at platforms B and D). The same `jid` can also
  legitimately reappear much later as another departure (line 94 → line 7, 38 min later). Deduplicate by
  `jid` **only within a few minutes**, keeping the first occurrence.
- **Cancellations**: `stbStop.dCncl = true` (not present in the recorded fixtures; tests derive a variant).
- **Disruption messages**: `common.himL` contains current notices (e.g. construction, bridge closures) — candidate
  for a later "Störungen" line in the widget.
- **Load**: 2 stops × 1 request per 30–60 s is a modest load; requests are cached server-side.

Recorded responses are stored in `tests/fixtures/insa_hafas/` and serve as test fixtures.

## Consequences

- Unofficial API: it may change or be blocked without notice. Mitigations: everything goes through the
  `DepartureProvider` interface; an optional live smoke test (`@pytest.mark.live`) detects format changes early;
  Transitous can be implemented as a schedule-only fallback provider if INSA becomes unavailable.
- If HAVAG/MDV publish an official realtime API later, switch to it.
