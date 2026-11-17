# ADR 0001: Technology stack and operations

- Status: accepted
- Date: 2026-11-09

## Context

The dashboard is displayed on an old Android tablet (Android version unknown) in a kiosk browser.
A headless Raspberry Pi 3b (1 GB RAM, arm64) is available as an always-on server. The code is written by an
AI agent and maintained by a developer who prefers mainstream, unexotic technology.
Development and tests happen exclusively in WSL; the Pi is only a deployment target.

## Decision

- **Client/server web app** instead of a native Android app: one central server, any number of displays,
  updates only on the server, credentials stay on the server, server-side caching of external APIs.
- **Python 3.14** (started on 3.12, upgraded 2026-11-17) **+ FastAPI + Jinja2 + HTMX 1.9.x** (vendored), plain CSS, no frontend build step.
  Server-side rendering keeps the client requirements minimal for old WebViews.
- **uv** for dependency management, **ruff** for linting/formatting, **pytest** + **respx** for tests.
- **Docker Compose** on the Pi. Images are cross-built for `linux/arm64` in WSL and transferred via
  `docker save | ssh … docker load`; no registry, no builds on the Pi.
- Server port **3274** (T9 for "DASH").

## Alternatives considered

- Native Android app without Pi: no server needed, but per-tablet installation, old API levels,
  credentials on the device, harder to test.
- TypeScript (Node + Svelte/React SPA): one language, but needs a build step and transpiling for old WebViews.
- JVM (Spring Boot / Ktor): solid, but heavy for 1 GB RAM.
- systemd + venv instead of Docker: slightly lighter, but more coupled to the host system.

## Consequences

- The Pi must run permanently; the tablet depends on Wi-Fi and the Pi being reachable.
- Interactivity is limited to what HTMX polling offers, which is sufficient for a read-only wall display.
