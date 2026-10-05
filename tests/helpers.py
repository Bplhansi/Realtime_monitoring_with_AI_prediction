import random

from sysmon.models import LogEvent


def traffic(start, seconds, rate=20, latency=100.0, err=0.0, seed=1):
    """Synthetic events for `seconds` seconds starting at integer second `start`."""
    rng = random.Random(seed + start)
    out = []
    for s in range(start, start + seconds):
        for _ in range(rate):
            failed = rng.random() < err
            out.append(LogEvent(s + rng.random() * 0.99, "api", "ERROR" if failed else "INFO",
                                max(1.0, rng.gauss(latency, latency * 0.1)),
                                500 if failed else 200))
    return out


def run(pipe, events):
    """Feed events, return every emitted result."""
    results = []
    for e in events:
        results += pipe.ingest(e)
    return results
