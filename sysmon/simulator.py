import math
import random

from .models import LogEvent

SCENARIOS = ("latency", "errors", "drift", "outage")


class LogSimulator:
    """Generates realistic web-service log traffic, with injectable faults."""

    def __init__(self, seed=None, services=("api", "auth", "checkout")):
        self.rng = random.Random(seed)
        self.services = services
        self.scenario = "normal"
        self.left = 0
        self.drift = 0.0
        self.t = 0

    def inject(self, scenario: str, seconds: int = 30):
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        self.scenario, self.left, self.drift = scenario, int(seconds), 0.0

    def tick(self, now: float) -> list:
        """Events for the one second starting at int(now)."""
        self.t += 1
        r = self.rng
        n = max(1, int(r.gauss(25, 3)))
        base = 130 + 20 * math.sin(self.t / 30)
        extra, err = 0.0, 0.01
        if self.scenario == "latency":
            extra = 380
        elif self.scenario == "errors":
            err = 0.4
        elif self.scenario == "drift":
            self.drift += 6
            extra = self.drift
        elif self.scenario == "outage":
            n = r.randint(0, 2)
        if self.scenario != "normal":
            self.left -= 1
            if self.left <= 0:
                self.scenario, self.drift = "normal", 0.0
        events = []
        for _ in range(n):
            failed = r.random() < err
            events.append(LogEvent(
                ts=int(now) + r.random() * 0.999,
                service=r.choice(self.services),
                level="ERROR" if failed else "INFO",
                latency_ms=max(5.0, r.gauss(base + extra, base * 0.15)),
                status=500 if failed else 200,
                message="upstream timeout" if failed else "request ok"))
        return events
