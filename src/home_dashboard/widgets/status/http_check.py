"""HealthCheck over HTTP(S): a GET must be answered with a 2xx status, see ADR 0005."""

from __future__ import annotations

import httpx

from home_dashboard.widgets.status.source import Unhealthy


class HttpHealthCheck:
    def __init__(self, http: httpx.Client, timeout_seconds: float) -> None:
        self._http = http
        self._timeout = httpx.Timeout(timeout_seconds)

    def check(self, url: str) -> None:
        try:
            # Redirects are not followed: a 3xx is not healthy (configure the final URL)
            response = self._http.get(url, timeout=self._timeout, follow_redirects=False)
        except httpx.HTTPError as error:
            raise Unhealthy(f"{type(error).__name__}: {error}") from error
        if not response.is_success:
            raise Unhealthy(f"HTTP {response.status_code}")
