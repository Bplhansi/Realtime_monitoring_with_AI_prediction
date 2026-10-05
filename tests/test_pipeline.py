from helpers import run, traffic
from sysmon.models import LogEvent
from sysmon.pipeline import Aggregator, Pipeline, make_window


def ev(ts, latency=100, status=200):
    return LogEvent(ts, "api", "INFO", latency, status)


def test_window_math():
    events = [ev(1, latency=i) for i in range(1, 101)]
    events.append(ev(1, 50, 500))
    w = make_window(1, events)
    assert w.count == 101 and w.errors == 1
    assert w.p95 == 95
    assert abs(w.error_rate - 1 / 101) < 1e-9


def test_aggregator_emits_after_lateness():
    agg = Aggregator(lateness=1)
    assert agg.add(ev(10.1)) == []
    assert agg.add(ev(11.2)) == []
    out = agg.add(ev(12.3))
    assert [w.ts for w in out] == [10]


def test_late_events_within_lateness_count_and_older_are_dropped():
    agg = Aggregator(lateness=1)
    agg.add(ev(10.1))
    agg.add(ev(11.1))
    agg.add(ev(10.9))                 # one second late: still accepted
    out = agg.add(ev(12.5))
    assert out[0].ts == 10 and out[0].count == 2
    agg.add(ev(5.0))                  # far too late
    assert agg.dropped == 1


def test_gaps_become_empty_windows():
    agg = Aggregator(lateness=0)
    agg.add(ev(10.1))
    out = agg.add(ev(14.1))
    assert [w.ts for w in out] == [10, 11, 12, 13]
    assert [w.count for w in out] == [1, 0, 0, 0]


def test_flush_emits_pending_windows():
    agg = Aggregator(lateness=5)
    agg.add(ev(10.1))
    agg.add(ev(11.1))
    assert [w.ts for w in agg.flush()] == [10, 11]


def test_quiet_traffic_raises_no_incidents():
    pipe = Pipeline()
    results = run(pipe, traffic(1000, 120))
    assert len(results) > 100
    assert pipe.incidents.snapshot() == []


def test_latency_spike_opens_then_resolves_an_incident():
    pipe = Pipeline()
    run(pipe, traffic(1000, 60))
    run(pipe, traffic(1060, 15, latency=550))
    opened = [i for i in pipe.incidents.snapshot() if i["metric"] == "p95_ms"]
    assert opened and opened[0]["severity"] == "critical"
    run(pipe, traffic(1075, 40))
    pipe.flush()
    assert "p95_ms" not in pipe.incidents.open
    assert pipe.incidents.closed[-1].resolved_at is not None


def test_error_burst_is_detected():
    pipe = Pipeline()
    run(pipe, traffic(2000, 60))
    run(pipe, traffic(2060, 12, err=0.5))
    assert "error_rate" in pipe.incidents.open


def test_outage_is_detected_as_a_traffic_drop():
    pipe = Pipeline()
    run(pipe, traffic(3000, 60))
    run(pipe, traffic(3060, 10, rate=1))
    pipe.flush()
    assert "rps" in pipe.incidents.open


def test_slow_drift_is_predicted_before_it_breaches():
    pipe = Pipeline()
    run(pipe, traffic(4000, 60))
    seen_watch = False
    for s in range(60):
        run(pipe, traffic(4060 + s, 1, latency=100 + 7 * s))
        inc = pipe.incidents.open.get("p95_ms")
        if inc and inc.severity == "watch":
            seen_watch = True
            break
    assert seen_watch
    assert pipe.history[-1]["p95_ms"] < pipe.cfg.limits["p95_ms"]


def test_forecast_and_history_are_exposed():
    pipe = Pipeline()
    run(pipe, traffic(5000, 30))
    assert len(pipe.forecast) == pipe.cfg.horizon
    assert 0 < len(pipe.history) <= pipe.cfg.history


def test_outage_incident_stays_open_while_the_outage_lasts():
    pipe = Pipeline()
    run(pipe, traffic(6000, 60))
    run(pipe, traffic(6060, 30, rate=1))
    assert "rps" in pipe.incidents.open
    run(pipe, traffic(6090, 30))
    pipe.flush()
    assert "rps" not in pipe.incidents.open


def test_simulated_normal_traffic_produces_no_false_incidents():
    from sysmon.simulator import LogSimulator
    for seed in (2, 42, 7):
        pipe, sim, now = Pipeline(), LogSimulator(seed=seed), 1_700_000_000
        for _ in range(4000):
            for e in sim.tick(now):
                pipe.ingest(e)
            now += 1
        assert pipe.incidents.snapshot() == [], f"seed {seed}"
