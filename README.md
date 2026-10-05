<div align="center">

# Real-Time System Monitor

**Spot problems in your service before your users do**

Streams logs in, flags abnormal behaviour, forecasts the next 30 seconds, and opens incidents on a live dashboard.

![Status](https://img.shields.io/badge/Status-Working%20Prototype-4F9CF9?style=for-the-badge&labelColor=0A1432)
![Stack](https://img.shields.io/badge/Stack-Python%20%7C%20FastAPI%20%7C%20SSE-4F9CF9?style=for-the-badge&labelColor=0A1432)
![Tests](https://img.shields.io/badge/Tests-52%20passing-4F9CF9?style=for-the-badge&labelColor=0A1432)

</div>

<!-- Add a screenshot of the dashboard here once you have run it:
![Dashboard](assets/dashboard.png)
-->

## 🔭 The Problem

Dashboards show you what already happened. By the time a fixed alert threshold trips, users have usually felt it, and the usual ways of catching problems each miss something.

- 📏 **Static thresholds**: "alert above 400 ms" ignores what is normal for your traffic, and fires late on a slow climb.
- 🔊 **Noisy alerts**: a single odd reading pages someone, so people learn to ignore the pages.
- 🕳️ **Silent failures**: when traffic drops to zero there are no slow requests to measure, so latency graphs look fine during an outage.

## 💡 The Solution

This project treats monitoring as a **forecasting problem**. It learns what normal looks like for each metric, predicts the next value, and raises an incident only when reality keeps disagreeing with the prediction. The same model projects 30 seconds ahead, so a slow degradation is flagged *before* it crosses your limit.

### How it works

```
logs ──► bounded queue ──► 1s windows ──► detectors ──► incidents ──► live stream ──► dashboard
(POST or   (backpressure)   (event time,    (forecast +    (open, escalate,   (SSE)
 simulator)                  late-tolerant)  anomaly flag)  resolve)
```

1. **Ingest:** logs arrive as JSON through `POST /api/ingest` or from the built-in simulator. A bounded queue pushes back with HTTP 429 when full, so a flood cannot exhaust memory.
2. **Window:** events are grouped into 1-second windows by the time they happened, not when they arrived. Slightly late lines still count, and empty seconds produce empty windows so an outage stays visible.
3. **Measure:** each window gives requests per second, p95 latency and error rate.
4. **Detect:** one Holt smoothing model per metric predicts the next value. A reading more than 4 standard deviations off is an anomaly. While anomalous, the model freezes its baseline, so a fault cannot teach it that broken is normal.
5. **Forecast:** the same model projects 30 seconds ahead with a widening 95% range.
6. **Escalate:** incidents open only on sustained evidence, never on one bad reading.

| Severity | Opens when |
|---|---|
| 🔴 **critical** | the value is above its limit for 2 windows |
| 🟠 **warning** | the metric is anomalous for 2 windows |
| 🟣 **watch** | the forecast crosses the limit within 20 s, 3 windows in a row, and the level is already at 60% of the limit |

Severity can escalate but not drop, and an incident resolves after 5 clean windows.

> The model is classical statistical forecasting, not a neural network. It needs no training data, runs in microseconds, and its decisions can be explained line by line.

## 🧰 Tech Stack

| **Component** | **Technology** | **Description** |
|---|---|---|
| **API** | FastAPI, Uvicorn | Ingestion, state, injection, and a server-sent events stream |
| **Pipeline** | Python `asyncio` | Bounded queue, event-time windowing, one worker |
| **Detection** | Holt linear smoothing | Anomaly flags and forecasts with confidence bands, written from scratch |
| **Incidents** | Python | Open, escalate and resolve rules per metric |
| **Dashboard** | HTML, Canvas, JavaScript | One file, no build step, light and dark themes |
| **Tests** | pytest, httpx | 52 tests, including a no-false-alarm soak |

## 🚀 Getting Started

```bash
git clone https://github.com/Bplhansi/Realtime_monitoring_with_AI_prediction.git
cd Realtime_monitoring_with_AI_prediction
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m sysmon
```

Open **http://localhost:8000**. A simulator generates traffic. Use the buttons to inject a latency spike, error burst, slow degradation or traffic outage, and watch an incident appear.

### Monitor real logs

Turn the simulator off and send events yourself:

```bash
SYSMON_SIMULATE=0 python -m sysmon

curl -X POST localhost:8000/api/ingest -H 'content-type: application/json' \
  -d '{"events":[{"ts":1700000000.2,"service":"api","level":"INFO","latency_ms":84,"status":200}]}'
```

Each event needs `ts` (unix seconds), `latency_ms` and `status`. Bad records are counted as `rejected` instead of failing the batch. Add `?wait=true` to block until processing finishes.

### API

| Endpoint | Purpose |
|---|---|
| `GET /` | Dashboard |
| `GET /api/state` | Recent windows, forecast, incidents, limits |
| `GET /api/stream` | Live updates (server-sent events) |
| `POST /api/ingest` | Send log events |
| `POST /api/inject` | Trigger a simulated fault |
| `GET /api/health` | Queue depth and counters |

### Run the tests

```bash
pytest
```

### Tune it

Limits, forecast horizon, lateness and sustain counts are in `sysmon/config.py`. The noise floor for each metric (`min_sigma`) is set in `Pipeline.__init__`. The defaults are a 400 ms p95 limit and a 10% error-rate limit.

## 📊 Measured Behaviour

Measured on simulated traffic, not production data:

| Scenario | Result |
|---|---|
| Latency spike, error burst, outage | Incident opens in about **4 to 9 seconds** |
| Slow degradation | A `watch` opens around **30 seconds** in, before p95 reaches the limit |
| Normal traffic | **2 false incidents** across 80 simulated hours |

Real services have daily cycles, deploys and heavier-tailed noise, so expect to retune thresholds on your own data.

## 🗺️ Roadmap

- [x] **Streaming ingestion** with a bounded queue and backpressure
- [x] **Event-time windowing** that tolerates late logs and visible outages
- [x] **Anomaly detection** with a baseline that is protected from faults
- [x] **30-second forecasts** with confidence bands and breach prediction
- [x] **Incident lifecycle:** open, escalate, resolve
- [x] **Live dashboard** over server-sent events
- [x] **Fault simulator** for demos and tests
- [x] **Test suite** covering every layer
- [ ] **Per-service metrics:** events already carry `service`, the pipeline does not split on it yet
- [ ] **Seasonality** so predictable daily peaks stop looking anomalous
- [ ] **Persistent storage** so incidents survive a restart
- [ ] **Notifications** to Slack or email when an incident opens
- [ ] **Multi-process scaling** with a shared queue and detector state

## 🙏 Acknowledgements

- [FastAPI](https://fastapi.tiangolo.com) and [Uvicorn](https://www.uvicorn.org) for the web layer
- Charles Holt's linear exponential smoothing, the forecasting method behind the detectors
- [pytest](https://pytest.org) and [httpx](https://www.python-httpx.org) for the tests

---

<div align="center">

Made by **Bplhansi**

</div>
