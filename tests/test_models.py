import json

import pytest

from sysmon.models import parse_event, parse_line

GOOD = {"ts": 1700000000.5, "service": "api", "level": "info", "latency_ms": 12.5, "status": 200}


def test_parse_valid_event():
    ev = parse_event(GOOD)
    assert ev.level == "INFO" and ev.status == 200 and ev.latency_ms == 12.5


def test_parse_line_roundtrip():
    assert parse_line(json.dumps(GOOD)).service == "api"


@pytest.mark.parametrize("bad", [
    {}, {"ts": 1, "latency_ms": 5},
    {**GOOD, "latency_ms": -1}, {**GOOD, "status": 999},
    {**GOOD, "ts": "later"}, [1, 2],
])
def test_rejects_bad_records(bad):
    with pytest.raises(ValueError):
        parse_event(bad)


def test_rejects_non_json_line():
    with pytest.raises(ValueError):
        parse_line("not json")
