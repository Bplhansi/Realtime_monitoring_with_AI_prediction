import pytest

from sysmon.simulator import LogSimulator


def test_seeded_runs_are_reproducible():
    a, b = LogSimulator(seed=7), LogSimulator(seed=7)
    ea, eb = a.tick(1000), b.tick(1000)
    assert [e.latency_ms for e in ea] == [e.latency_ms for e in eb]


def test_events_fall_within_the_requested_second():
    for e in LogSimulator(seed=1).tick(1234.7):
        assert 1234 <= e.ts < 1235


def test_error_scenario_produces_5xx_and_then_recovers():
    sim = LogSimulator(seed=2)
    sim.inject("errors", seconds=3)
    errs = [e for _ in range(3) for e in sim.tick(1000) if e.status == 500]
    assert len(errs) > 10
    assert sim.scenario == "normal"


def test_outage_cuts_traffic():
    sim = LogSimulator(seed=3)
    sim.inject("outage", seconds=5)
    assert all(len(sim.tick(1000)) <= 2 for _ in range(5))


def test_unknown_scenario_rejected():
    with pytest.raises(ValueError):
        LogSimulator().inject("meteor")
