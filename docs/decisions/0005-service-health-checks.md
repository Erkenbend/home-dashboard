# ADR 0005: Service health checks from the dashboard server

- Status: accepted
- Date: 2026-11-21

## Context

The header shows the health of the services in the home network (FR-5): green, yellow (last check
failed) or red (several checks in a row failed). The checks are plain HTTP requests expecting a 2xx
status. The tablet only talks to the dashboard server, so the server has to run them. Open questions:
when the checks run, what counts as a failure, and how a container reaches services on its own host.

## Decision

- **Checks run on demand, driven by the widget's polling** (`status.refresh_seconds`), at most once per
  `status.check_seconds` for all displays together, like the upstream fetches of the other widgets.
  No background thread: no lifecycle to manage, and the injected `Clock` makes the failure counting
  fully testable. A check round is serialized with a lock, so two displays polling at the same moment
  do not check twice.
- **All services are checked in parallel** (thread pool per round) with a short timeout
  (`status.timeout_seconds`, default 5 s, max. 20 s), so one hanging service neither delays the others
  nor runs into the tablet's HTMX timeout (30 s).
- **Failure = anything but a 2xx answer** to a `GET`: other status codes, connection errors, timeouts,
  and also redirects (they are not followed; configure the final URL).
- The state is the **number of consecutive failed checks** per service, kept in memory: 0 green,
  1 yellow, 2+ red. A restart of the dashboard starts from scratch, which is fine for a display.
- The checks go through a `HealthCheck` interface (`check(url)`), the concrete one uses the shared
  `httpx.Client`.
- In Docker, `localhost` is the container. `compose.yaml` maps `host.docker.internal` to the host
  (`host-gateway`), so services on the Pi itself are checked as `http://host.docker.internal:<port>/…`.

## Consequences

- While no display is polling, nothing is checked; the first poll afterwards checks right away, so the
  bubbles never show an old state for long. The counter counts checks, not minutes: "red" means at least
  `check_seconds` of failures.
- The first page load waits for the first check round (at most `timeout_seconds`).
- Services bound to `127.0.0.1` on the Pi are not reachable from the container via
  `host.docker.internal`; they need to listen on the LAN or Docker bridge address.
- No notification or history: this is a glance at the wall, not an alerting system.
