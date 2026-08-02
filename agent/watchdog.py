"""Non-destructive watchdog for slow local model decisions."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable


class ModelStallError(TimeoutError):
    """The decision became stale; the worker is deliberately not killed."""


class DecisionWatchdog:
    def __init__(self, warning_seconds: float, bark_interval_seconds: float, max_seconds: float):
        self.warning_seconds = max(0.01, float(warning_seconds))
        self.bark_interval_seconds = max(0.01, float(bark_interval_seconds))
        self.max_seconds = min(295.0, max(self.warning_seconds, float(max_seconds)))

    def run(self, operation: Callable[[], object], on_bark: Callable[[float], None]):
        results: queue.Queue = queue.Queue(maxsize=1)

        def worker() -> None:
            try:
                results.put((True, operation()))
            except BaseException as exc:  # transported to the orchestrator thread
                results.put((False, exc))

        thread = threading.Thread(target=worker, name="local-model-decision", daemon=True)
        started = time.monotonic()
        next_bark = self.warning_seconds
        thread.start()
        while True:
            elapsed = time.monotonic() - started
            until_bark = max(0.001, next_bark - elapsed)
            remaining = min(0.25, max(0.001, self.max_seconds - elapsed), until_bark)
            try:
                ok, value = results.get(timeout=remaining)
                if ok:
                    return value, time.monotonic() - started
                raise value
            except queue.Empty:
                elapsed = time.monotonic() - started
                if elapsed >= next_bark:
                    on_bark(elapsed)
                    next_bark += self.bark_interval_seconds
                if elapsed >= self.max_seconds:
                    raise ModelStallError(
                        f"local model produced no decision within {self.max_seconds:.1f}s; "
                        "late result will be discarded without killing the provider"
                    )
