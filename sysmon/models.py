import json
from dataclasses import dataclass


@dataclass
class LogEvent:
    ts: float
    service: str
    level: str
    latency_ms: float
    status: int
    message: str = ""


def parse_event(d: dict) -> LogEvent:
    """Validate a decoded log record. Raises ValueError on bad input."""
    if not isinstance(d, dict):
        raise ValueError("record must be an object")
    try:
        ts = float(d["ts"])
        latency = float(d["latency_ms"])
        status = int(d["status"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing or invalid field: {exc}") from exc
    if latency < 0 or ts <= 0 or not 100 <= status <= 599:
        raise ValueError("field out of range")
    return LogEvent(ts, str(d.get("service", "unknown")), str(d.get("level", "INFO")).upper(),
                    latency, status, str(d.get("message", "")))


def parse_line(line: str) -> LogEvent:
    """Parse one JSON log line."""
    try:
        return parse_event(json.loads(line))
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc
