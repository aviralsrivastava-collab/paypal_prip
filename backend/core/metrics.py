import threading
from typing import Any, Dict, List, Optional, Protocol


class MetricsCollector(Protocol):
    """
    Provider-neutral metrics collection interface.
    Decouples domain services from specific monitoring agents (Prometheus, Datadog, StatsD).
    """

    def increment(
        self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None
    ) -> None:
        ...

    def timing(
        self, name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        ...

    def gauge(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        ...

    def get_metrics(self) -> Dict[str, Any]:
        ...

    def reset(self) -> None:
        ...


class InMemoryMetricsCollector:
    """
    Thread-safe in-memory metrics collector for local development, demo visibility, and automated testing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._timings: Dict[str, List[float]] = {}

    def increment(
        self, name: str, value: int = 1, tags: Optional[Dict[str, str]] = None
    ) -> None:
        key = self._format_key(name, tags)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def timing(
        self, name: str, duration_ms: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        key = self._format_key(name, tags)
        with self._lock:
            if key not in self._timings:
                self._timings[key] = []
            self._timings[key].append(duration_ms)

    def gauge(
        self, name: str, value: float, tags: Optional[Dict[str, str]] = None
    ) -> None:
        key = self._format_key(name, tags)
        with self._lock:
            self._gauges[key] = value

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            timing_stats: Dict[str, Dict[str, float]] = {}
            for k, vals in self._timings.items():
                if vals:
                    timing_stats[k] = {
                        "count": len(vals),
                        "avg_ms": round(sum(vals) / len(vals), 2),
                        "min_ms": round(min(vals), 2),
                        "max_ms": round(max(vals), 2),
                    }
                else:
                    timing_stats[k] = {"count": 0, "avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}

            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timings": timing_stats,
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timings.clear()

    @staticmethod
    def _format_key(name: str, tags: Optional[Dict[str, str]] = None) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"


_metrics_instance: InMemoryMetricsCollector = InMemoryMetricsCollector()


def get_metrics_collector() -> InMemoryMetricsCollector:
    return _metrics_instance
