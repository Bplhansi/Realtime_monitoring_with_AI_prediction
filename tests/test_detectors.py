import random

import pytest

from sysmon.detectors import HoltDetector


def steady(det, n=60, base=100.0, noise=2.0, seed=0):
    rng = random.Random(seed)
    return [det.update(rng.gauss(base, noise)) for _ in range(n)]


def test_no_anomalies_on_steady_signal():
    readings = steady(HoltDetector(min_sigma=5))
    assert not any(r.anomaly for r in readings)


def test_flags_a_spike_after_warmup():
    det = HoltDetector(min_sigma=5)
    steady(det)
    assert det.update(300).anomaly


def test_never_flags_during_warmup():
    det = HoltDetector(warmup=20, min_sigma=5)
    steady(det, n=5)
    assert not det.update(1000).anomaly


def test_one_sided_detector_ignores_drops():
    det = HoltDetector(min_sigma=5, direction="up")
    steady(det)
    assert not det.update(0).anomaly
    assert det.update(500).anomaly


def test_two_sided_detector_flags_drops():
    det = HoltDetector(min_sigma=5, direction="both")
    steady(det)
    assert det.update(0).anomaly


def test_spike_does_not_corrupt_baseline():
    det = HoltDetector(min_sigma=5)
    steady(det)
    det.update(1000)
    assert abs(det.level - 100) < 40


def test_forecast_follows_a_rising_trend_and_band_widens():
    det = HoltDetector(min_sigma=1)
    for i in range(60):
        det.update(100 + 2 * i)
    fc = det.forecast(10)
    assert fc[-1]["m"] > fc[0]["m"] > 200
    assert (fc[-1]["hi"] - fc[-1]["lo"]) > (fc[0]["hi"] - fc[0]["lo"])


def test_steps_to_exceed():
    det = HoltDetector(min_sigma=1)
    for i in range(60):
        det.update(100 + 2 * i)
    k = det.steps_to_exceed(det.level + det.trend * 7.5, 30)
    assert k == 8
    assert det.steps_to_exceed(1e9, 30) is None


def test_steps_to_exceed_is_silent_during_warmup():
    det = HoltDetector(warmup=20)
    for i in range(5):
        det.update(100 + 50 * i)
    assert det.steps_to_exceed(10, 30) is None


def test_invalid_direction_rejected():
    with pytest.raises(ValueError):
        HoltDetector(direction="sideways")


def test_baseline_is_frozen_during_a_sustained_anomaly():
    det = HoltDetector(min_sigma=5, max_freeze=60)
    steady(det)
    flags = [det.update(400).anomaly for _ in range(30)]
    assert all(flags)
    assert abs(det.level - 100) < 10


def test_a_very_long_shift_becomes_the_new_normal():
    det = HoltDetector(min_sigma=5, max_freeze=10)
    steady(det)
    flags = [det.update(400).anomaly for _ in range(30)]
    assert flags[0] and not flags[-1]
    assert abs(det.level - 400) < 20
