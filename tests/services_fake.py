"""Fake health check endpoints of services in the home network (via respx)."""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Callable

import httpx
import respx

type Handler = Callable[[httpx.Request], httpx.Response]


class ServicesFake:
    """Every registered URL answers 200 until a test says otherwise."""

    def __init__(self, router: respx.Router) -> None:
        self._router = router
        self._answers: dict[str, httpx.Response | Exception | Handler] = {}
        self._lock = threading.Lock()  # checks run in parallel threads
        self.requests: list[httpx.Request] = []

    def add(self, url: str) -> str:
        self._answers[url] = httpx.Response(200, text="OK")
        self._router.get(url).mock(side_effect=self._respond)
        return url

    def answer(self, url: str, status: int, **kwargs) -> None:
        self._answers[url] = httpx.Response(status, **kwargs)

    def fail(self, url: str, error: Exception) -> None:
        self._answers[url] = error

    def handle(self, url: str, handler: Handler) -> None:
        """Answer with `handler(request)`, called in the checking thread."""
        self._answers[url] = handler

    def checks(self, url: str) -> int:
        return Counter(str(request.url) for request in self.requests)[url]

    def _respond(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.requests.append(request)
        answer = self._answers[str(request.url)]
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, httpx.Response) else answer(request)
