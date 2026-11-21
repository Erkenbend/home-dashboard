"""Interface between the services status widget and the way a service is checked."""

from __future__ import annotations

from typing import Protocol


class Unhealthy(Exception):
    """The service did not pass its health check; the message says why."""


class HealthCheck(Protocol):
    def check(self, url: str) -> None:
        """Return if the service at `url` is healthy, raise `Unhealthy` otherwise."""
        ...
