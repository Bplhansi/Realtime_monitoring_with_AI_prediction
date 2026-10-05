import asyncio
import json
import os
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .config import Config
from .models import parse_event
from .pipeline import Pipeline
from .simulator import LogSimulator

STATIC = Path(__file__).parent / "static"


class IngestBody(BaseModel):
    events: list[dict]


class InjectBody(BaseModel):
    scenario: Literal["latency", "errors", "drift", "outage"]
    seconds: int = 30


def create_app(simulate: bool = None, cfg: Config = None) -> FastAPI:
    if simulate is None:
        simulate = os.getenv("SYSMON_SIMULATE", "1") != "0"
    pipeline = Pipeline(cfg)
    sim = LogSimulator()
    queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)  # bounded: ingest pushes back when full
    subscribers: set = set()

    def publish(msg: dict):
        for q in list(subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # a slow dashboard misses updates instead of stalling ingestion

    def handle(ev):
        for out in pipeline.ingest(ev):
            publish({"type": "point", "point": out["point"], "forecast": out["forecast"]})
            for inc in out["incidents"]:
                publish({"type": "incident", **inc})

    async def worker():
        while True:
            ev = await queue.get()
            try:
                handle(ev)
            finally:
                queue.task_done()

    async def generator():
        while True:
            for ev in sim.tick(time.time()):
                with suppress(asyncio.QueueFull):
                    queue.put_nowait(ev)
            await asyncio.sleep(1)

    @asynccontextmanager
    async def lifespan(app):
        tasks = [asyncio.create_task(worker())]
        if simulate:
            tasks.append(asyncio.create_task(generator()))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="sysmon", lifespan=lifespan)
    app.state.pipeline, app.state.sim = pipeline, sim

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True, "queue": queue.qsize(), "events": pipeline.events_seen,
                "late_dropped": pipeline.late_dropped}

    @app.get("/api/state")
    def state():
        return {"points": list(pipeline.history), "forecast": pipeline.forecast,
                "incidents": pipeline.incidents.snapshot(), "limits": pipeline.cfg.limits,
                "scenario": sim.scenario}

    @app.post("/api/ingest")
    async def ingest(body: IngestBody, wait: bool = False):
        accepted = rejected = 0
        for raw in body.events:
            try:
                ev = parse_event(raw)
            except ValueError:
                rejected += 1
                continue
            try:
                queue.put_nowait(ev)
                accepted += 1
            except asyncio.QueueFull:
                raise HTTPException(429, "ingest queue is full, retry shortly")
        if wait:
            await queue.join()
        return {"accepted": accepted, "rejected": rejected}

    @app.post("/api/inject")
    def inject(body: InjectBody):
        sim.inject(body.scenario, body.seconds)
        return {"scenario": sim.scenario, "seconds": body.seconds}

    @app.get("/api/stream")
    async def stream():
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        subscribers.add(q)

        async def gen():
            try:
                while True:
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=15)
                        yield f"data: {json.dumps(msg)}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                subscribers.discard(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    return app
