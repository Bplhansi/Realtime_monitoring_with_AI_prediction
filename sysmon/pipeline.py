import math
from collections import deque
from dataclasses import dataclass

from .config import Config
from .detectors import HoltDetector
from .incidents import IncidentManager
from .models import LogEvent


@dataclass
class Window:
    ts: int
    count: int
    errors: int
    p95: float
    mean: float

    @property
    def error_rate(self) -> float:
        return self.errors / self.count if self.count else 0.0


def make_window(ts: int, events: list) -> Window:
    if not events:
        return Window(ts, 0, 0, 0.0, 0.0)
    lat = sorted(e.latency_ms for e in events)
    p95 = lat[max(0, math.ceil(0.95 * len(lat)) - 1)]
    errors = sum(1 for e in events if e.status >= 500)
    return Window(ts, len(events), errors, p95, sum(lat) / len(lat))


class Aggregator:
    """Groups events into 1-second windows by event time.

    A window is emitted once the newest event is more than `lateness` seconds past it.
    Seconds with no traffic are emitted as empty windows so outages stay visible.
    Events older than the watermark are counted in `dropped`.
    """

    def __init__(self, lateness=1):
        self.lateness = lateness
        self.buckets = {}
        self.max_bucket = None
        self.last_emitted = None
        self.dropped = 0

    def add(self, ev: LogEvent) -> list:
        b = int(ev.ts)
        if self.max_bucket is not None and self.max_bucket - b > self.lateness:
            self.dropped += 1
            return []
        self.buckets.setdefault(b, []).append(ev)
        self.max_bucket = b if self.max_bucket is None else max(self.max_bucket, b)
        return self._emit(self.max_bucket - self.lateness - 1)

    def flush(self) -> list:
        return self._emit(self.max_bucket) if self.max_bucket is not None else []

    def _emit(self, upto) -> list:
        out = []
        if not self.buckets:
            return out
        start = self.last_emitted + 1 if self.last_emitted is not None else min(self.buckets)
        for sec in range(start, upto + 1):
            out.append(make_window(sec, self.buckets.pop(sec, [])))
            self.last_emitted = sec
        return out


class Pipeline:
    """log event -> 1s window -> detectors -> incidents."""

    def __init__(self, cfg: Config = None):
        self.cfg = cfg or Config()
        self.agg = Aggregator(self.cfg.lateness)
        self.det = {
            "rps": HoltDetector(min_sigma=3.0),
            "p95_ms": HoltDetector(min_sigma=10.0, direction="up"),
            "error_rate": HoltDetector(min_sigma=0.04, direction="up"),
        }
        self.incidents = IncidentManager(self.cfg)
        self.history = deque(maxlen=self.cfg.history)
        self.forecast = []
        self.events_seen = 0

    @property
    def late_dropped(self) -> int:
        return self.agg.dropped

    def ingest(self, ev: LogEvent) -> list:
        self.events_seen += 1
        return [self.process_window(w) for w in self.agg.add(ev)]

    def flush(self) -> list:
        return [self.process_window(w) for w in self.agg.flush()]

    def process_window(self, w: Window) -> dict:
        series = [("rps", float(w.count))]
        if w.count:
            series += [("p95_ms", w.p95), ("error_rate", w.error_rate)]
        metrics, incident_events = {}, []
        for name, value in series:
            det = self.det[name]
            reading = det.update(value)
            limit = self.cfg.limits.get(name)
            breach = None
            if limit is not None and det.level >= self.cfg.predict_min_fraction * limit:
                breach = det.steps_to_exceed(limit, self.cfg.horizon)
            metrics[name] = {"value": round(value, 4), "expected": round(reading.expected, 4),
                             "anomaly": reading.anomaly, "breach_in": breach}
            incident_events += self.incidents.observe(w.ts, name, value, reading.anomaly, breach, limit)
        point = {"ts": w.ts, "rps": w.count,
                 "p95_ms": round(w.p95, 1) if w.count else None,
                 "error_rate": round(w.error_rate, 4) if w.count else None,
                 "metrics": metrics}
        self.history.append(point)
        self.forecast = self.det["p95_ms"].forecast(self.cfg.horizon)
        return {"point": point, "forecast": self.forecast, "incidents": incident_events}
