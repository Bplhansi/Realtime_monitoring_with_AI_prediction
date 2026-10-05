import pytest
from fastapi.testclient import TestClient

from helpers import traffic
from sysmon.app import create_app


def payload(events):
    return {"events": [{"ts": e.ts, "service": e.service, "level": e.level,
                        "latency_ms": e.latency_ms, "status": e.status} for e in events]}


@pytest.fixture
def client():
    with TestClient(create_app(simulate=False)) as c:
        yield c


def test_health_and_index(client):
    assert client.get("/api/health").json()["ok"] is True
    page = client.get("/")
    assert page.status_code == 200 and "System monitor" in page.text


def test_ingest_produces_points_in_state(client):
    r = client.post("/api/ingest?wait=true", json=payload(traffic(1000, 30)))
    assert r.json() == {"accepted": 600, "rejected": 0}
    state = client.get("/api/state").json()
    assert len(state["points"]) > 20
    assert len(state["forecast"]) == 30
    assert state["limits"]["p95_ms"] == 400.0


def test_bad_records_are_counted_not_fatal(client):
    body = payload(traffic(1000, 1, rate=2))
    body["events"] += [{"ts": 1}, {"nope": True}]
    r = client.post("/api/ingest?wait=true", json=body)
    assert r.json() == {"accepted": 2, "rejected": 2}


def test_incident_flows_through_api(client):
    client.post("/api/ingest?wait=true", json=payload(traffic(1000, 60)))
    client.post("/api/ingest?wait=true", json=payload(traffic(1060, 15, latency=550)))
    incidents = client.get("/api/state").json()["incidents"]
    assert any(i["metric"] == "p95_ms" and i["severity"] == "critical" for i in incidents)


def test_inject_validates_scenario(client):
    assert client.post("/api/inject", json={"scenario": "latency", "seconds": 5}).status_code == 200
    assert client.get("/api/state").json()["scenario"] == "latency"
    assert client.post("/api/inject", json={"scenario": "meteor"}).status_code == 422


def test_ingest_rejects_malformed_body(client):
    assert client.post("/api/ingest", json={"wrong": 1}).status_code == 422
