"""Services status widget logic: consecutive failed health checks per service, see ADR 0005."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from home_dashboard.cache import fetch_interval
from home_dashboard.clock import Clock
from home_dashboard.config import ServiceConfig, StatusConfig
from home_dashboard.widgets.status.source import HealthCheck

log = logging.getLogger(__name__)

FAILING_AFTER = 2
"""Failed checks in a row from which a service is shown red (one failure: yellow)"""
MAX_PARALLEL_CHECKS = 8


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    state: str
    """ok, warning (last check failed), failing (FAILING_AFTER or more checks in a row failed)"""
    failures: int
    """Failed checks in a row"""

    @property
    def description(self) -> str:
        if self.failures == 0:
            return "erreichbar"
        if self.failures == 1:
            return "letzte Prüfung fehlgeschlagen"
        return f"{self.failures} Prüfungen in Folge fehlgeschlagen"


@dataclass(frozen=True)
class StatusView:
    services: list[ServiceStatus]
    checked_at: datetime


def state(failures: int) -> str:
    if failures == 0:
        return "ok"
    return "warning" if failures < FAILING_AFTER else "failing"


class StatusService:
    def __init__(self, config: StatusConfig, check: HealthCheck, clock: Clock) -> None:
        self._config = config
        self._check = check
        self._clock = clock
        self._failures = [0] * len(config.services)
        self._checked_at: datetime | None = None
        self._lock = threading.Lock()  # one check round at a time, also with several displays

    def view(self) -> StatusView:
        with self._lock:
            now = self._clock.now()
            due = fetch_interval(self._config.check_seconds)
            if self._checked_at is None or now - self._checked_at >= due:
                self._check_all()
                self._checked_at = now
            return StatusView(
                services=[
                    ServiceStatus(service.name, state(failures), failures)
                    for service, failures in zip(self._config.services, self._failures, strict=True)
                ],
                checked_at=self._checked_at,
            )

    def _check_all(self) -> None:
        """All services in parallel: a hanging one costs at most one timeout for the whole round."""
        services = self._config.services
        workers = min(MAX_PARALLEL_CHECKS, len(services))
        with ThreadPoolExecutor(workers, thread_name_prefix="health-check") as pool:
            errors = list(pool.map(self._error, services))
        for index, (service, error) in enumerate(zip(services, errors, strict=True)):
            if error is None:
                if self._failures[index]:
                    log.info("%s is healthy again", service.name)
                self._failures[index] = 0
            else:
                if not self._failures[index]:
                    log.warning("health check of %s failed: %s", service.name, error)
                self._failures[index] += 1

    def _error(self, service: ServiceConfig) -> str | None:
        """None if healthy, otherwise why not."""
        try:
            self._check.check(service.url)
        except Exception as error:  # Unhealthy, but also a broken check must not break the widget
            return str(error) or type(error).__name__
        return None
