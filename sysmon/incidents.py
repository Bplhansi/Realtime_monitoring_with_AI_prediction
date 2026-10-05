import itertools
from dataclasses import asdict, dataclass

RANK = {"watch": 1, "warning": 2, "critical": 3}


@dataclass
class Incident:
    id: int
    metric: str
    severity: str
    reason: str
    opened_at: int
    peak: float
    resolved_at: int = None


class IncidentManager:
    """Turns per-window detector output into incidents with open/escalate/resolve rules.

    critical: value above its limit for `sustain` windows
    warning:  anomalous for `sustain` windows
    watch:    forecast crosses the limit soon for `sustain_predicted` windows
    One incident per metric; it resolves after `resolve_after` clean windows.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.open = {}
        self.closed = []
        self._state = {}
        self._ids = itertools.count(1)

    def observe(self, ts, metric, value, anomaly, breach_in, limit):
        cfg = self.cfg
        st = self._state.setdefault(metric, {"over": 0, "anom": 0, "pred": 0, "clean": 0})
        st["over"] = st["over"] + 1 if limit is not None and value > limit else 0
        st["anom"] = st["anom"] + 1 if anomaly else 0
        near = breach_in is not None and breach_in <= cfg.predicted_within
        st["pred"] = st["pred"] + 1 if near else 0

        sev = reason = None
        if st["over"] >= cfg.sustain:
            sev, reason = "critical", f"{metric} is above its limit of {limit}"
        elif st["anom"] >= cfg.sustain:
            sev, reason = "warning", f"{metric} is behaving abnormally"
        elif st["pred"] >= cfg.sustain_predicted:
            sev, reason = "watch", f"{metric} is forecast to pass {limit} in about {breach_in}s"

        inc, events = self.open.get(metric), []
        if sev:
            st["clean"] = 0
            if inc is None:
                inc = Incident(next(self._ids), metric, sev, reason, ts, value)
                self.open[metric] = inc
                events.append({"type": "opened", "incident": asdict(inc)})
            else:
                inc.peak = max(inc.peak, value)
                if RANK[sev] > RANK[inc.severity]:
                    inc.severity, inc.reason = sev, reason
                    events.append({"type": "escalated", "incident": asdict(inc)})
        elif inc:
            st["clean"] += 1
            if st["clean"] >= cfg.resolve_after:
                inc.resolved_at = ts
                del self.open[metric]
                self.closed.append(inc)
                self.closed = self.closed[-50:]
                events.append({"type": "resolved", "incident": asdict(inc)})
        return events

    def snapshot(self):
        return [asdict(i) for i in self.closed[-20:]] + [asdict(i) for i in self.open.values()]
