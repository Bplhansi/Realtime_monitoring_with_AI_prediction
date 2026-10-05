from sysmon.config import Config
from sysmon.incidents import IncidentManager


def mgr():
    return IncidentManager(Config(sustain=2, sustain_predicted=3, resolve_after=3))


def feed(m, n, value=1.0, anomaly=False, breach=None, limit=None, start=0):
    events = []
    for i in range(n):
        events += m.observe(start + i, "p95_ms", value, anomaly, breach, limit)
    return events


def test_single_anomaly_does_not_open():
    m = mgr()
    assert feed(m, 1, anomaly=True) == []


def test_sustained_anomaly_opens_a_warning():
    m = mgr()
    events = feed(m, 2, anomaly=True)
    assert [e["type"] for e in events] == ["opened"]
    assert m.open["p95_ms"].severity == "warning"


def test_limit_breach_escalates_to_critical():
    m = mgr()
    feed(m, 2, anomaly=True)
    events = feed(m, 2, value=500, anomaly=True, limit=400, start=2)
    assert events[-1]["type"] == "escalated"
    assert m.open["p95_ms"].severity == "critical"
    assert m.open["p95_ms"].peak == 500


def test_forecast_breach_opens_a_watch_only_when_close_and_sustained():
    m = mgr()
    assert feed(m, 3, breach=40, limit=400) == []          # too far away
    events = feed(m, 3, breach=10, limit=400)
    assert [e["type"] for e in events] == ["opened"]
    assert m.open["p95_ms"].severity == "watch"


def test_resolves_after_clean_windows():
    m = mgr()
    feed(m, 2, anomaly=True)
    events = feed(m, 3, start=2)
    assert events[-1]["type"] == "resolved"
    assert "p95_ms" not in m.open and len(m.closed) == 1


def test_a_bad_window_resets_the_clean_streak():
    m = mgr()
    feed(m, 2, anomaly=True)
    feed(m, 2, start=2)
    feed(m, 2, anomaly=True, start=4)
    assert "p95_ms" in m.open


def test_ids_increase_and_metrics_are_independent():
    m = mgr()
    for i in range(2):
        m.observe(i, "p95_ms", 1, True, None, None)
        m.observe(i, "rps", 1, True, None, None)
    ids = sorted(i.id for i in m.open.values())
    assert ids == [1, 2]
