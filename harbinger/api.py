"""HTTP surface: the page, the state document, and the agent's write endpoint."""

from __future__ import annotations

import secrets

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Config
from .state import SlotValidationError, StateStore


def create_app(config: Config, store: StateStore) -> FastAPI:
    app = FastAPI(title="Harbinger", docs_url=None, redoc_url=None)

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
