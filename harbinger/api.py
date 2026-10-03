"""HTTP surface: the page, the state document, and the agent's write endpoint."""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .collectors import build_collectors, make_client, run_collector
from .config import Config
from .state import SlotValidationError, StateStore

log = logging.getLogger("harbinger.api")


def create_app(config: Config, store: StateStore) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        collectors = build_collectors(config)
        tasks: list[asyncio.Task] = []
        client = make_client() if collectors else None
        for c in collectors:
            tasks.append(asyncio.create_task(run_collector(c, store, client), name=f"collector:{c.name}"))
            log.info("collector %s -> slot %s every %ss", c.name, c.slot, c.interval_s)
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if client:
                await client.aclose()

    app = FastAPI(title="Harbinger", docs_url=None, redoc_url=None, lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "slots": store.ages()}

    @app.get("/api/state")
    def state() -> JSONResponse:
        return JSONResponse(store.document(), headers={"Cache-Control": "no-store"})

    @app.put("/api/slots/{slot}", status_code=204)
    async def put_slot(slot: str, request: Request) -> Response:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "bearer token required", headers={"WWW-Authenticate": "Bearer"})
        if not config.agent_token:
            raise HTTPException(403, "agent token is not configured on the server")
        if not secrets.compare_digest(auth[7:].strip(), config.agent_token):
            raise HTTPException(403, "bad token")
        if slot not in config.writable_slots or slot not in store.slot_names:
            raise HTTPException(404, f"slot {slot!r} is not agent-writable")
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "body is not valid JSON")
        try:
            store.set_slot(slot, body)
        except SlotValidationError as e:
            raise HTTPException(400, str(e))
        return Response(status_code=204)

    app.mount("/", StaticFiles(directory=config.web_dir, html=True), name="web")
    return app
