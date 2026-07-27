from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.ip_cache import IpCache
from app.models import DashboardPayload, NoteUpdate
from app.note_store import NoteStore
from app.pbs import PbsClient
from app.proxmox import ProxmoxClient
from app.service import DashboardService

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


async def refresh_loop(service: DashboardService, interval: int) -> None:
    while True:
        try:
            await service.get_dashboard(force=True)
        except Exception:
            pass
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    ip_cache = IpCache(settings.ip_cache_file)
    notes = NoteStore(settings.notes_file)
    pve_clients = [ProxmoxClient(settings, instance, ip_cache, notes) for instance in settings.load_pve_instances()]
    pbs = PbsClient(settings)
    service = DashboardService(settings, pve_clients, pbs)
    app.state.settings = settings
    app.state.service = service
    app.state.notes = notes
    task = asyncio.create_task(refresh_loop(service, settings.refresh_seconds))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await asyncio.gather(*(client.close() for client in pve_clients), return_exceptions=True)
        await pbs.close()


app = FastAPI(title="Proxmox PBS Dashboard", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    if request.url.path.startswith("/api/") or request.url.path == "/health":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    return TEMPLATES.TemplateResponse(request=request, name="index.html", context={"title": settings.dashboard_title, "refresh_seconds": settings.refresh_seconds})


@app.get("/api/dashboard", response_model=DashboardPayload)
async def dashboard(request: Request) -> DashboardPayload:
    try:
        return await request.app.state.service.get_dashboard()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/refresh", response_model=DashboardPayload)
async def refresh(request: Request) -> DashboardPayload:
    try:
        return await request.app.state.service.get_dashboard(force=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.put("/api/notes/{pve_id}/{vmid}")
async def save_note(pve_id: str, vmid: int, body: NoteUpdate, request: Request) -> dict[str, object]:
    note = request.app.state.notes.set(pve_id, vmid, body.note)
    service: DashboardService = request.app.state.service
    if service._cached:
        for guest in service._cached.vms:
            if guest.pve_id == pve_id and guest.vmid == vmid:
                guest.note = note
    return {"ok": True, "pve_id": pve_id, "vmid": vmid, "note": note}


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    try:
        payload = await request.app.state.service.get_dashboard()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": all(source.ok for source in payload.pve) and payload.pbs.ok, "pve": [source.model_dump() for source in payload.pve], "pbs": payload.pbs.model_dump(), "updated_at": payload.updated_at, "stale": payload.stale}
