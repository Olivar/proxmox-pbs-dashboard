from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.auth import COOKIE_NAME, create_session, read_session, require_csrf, verify_password
from app.config import get_settings
from app.ip_cache import IpCache
from app.models import DashboardPayload, NoteUpdate, PveSummary
from app.note_store import NoteStore
from app.operations import router as operations_router
from app.pbs import PbsClient
from app.proxmox import ProxmoxClient
from app.service import DashboardService
from app.settings_store import masked_pbs_settings, masked_pve_settings, masked_settings, write_env
from app.version import APP_VERSION

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
PUBLIC_PATHS = {"/login", "/api/login", "/health", "/manifest.webmanifest", "/sw.js"}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class SettingsUpdate(BaseModel):
    values: dict[str, str]
    pves: list[dict[str, Any]]
    pbses: list[dict[str, Any]]


async def refresh_loop(service: DashboardService, interval: int) -> None:
    while True:
        try:
            await service.get_dashboard(force=True)
        except Exception:
            pass
        await asyncio.sleep(interval)


async def restart_after_settings_save() -> None:
    # Aguarda a resposta HTTP chegar ao navegador antes de encerrar o worker.
    await asyncio.sleep(0.8)
    os._exit(75)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    ip_cache = IpCache(settings.ip_cache_file)
    notes = NoteStore(settings.notes_file)
    pve_clients = [ProxmoxClient(settings, instance, ip_cache, notes) for instance in settings.load_pve_instances()]
    pbs_clients = [PbsClient(settings, instance) for instance in settings.load_pbs_instances()]
    service = DashboardService(settings, pve_clients, pbs_clients)
    app.state.settings = settings
    app.state.service = service
    app.state.notes = notes
    app.state.pve_clients = {client.instance.id: client for client in pve_clients}
    task = asyncio.create_task(refresh_loop(service, settings.refresh_seconds))
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await asyncio.gather(*(client.close() for client in pve_clients), return_exceptions=True)
        await asyncio.gather(*(client.close() for client in pbs_clients), return_exceptions=True)


app = FastAPI(title="Proxmox PBS Dashboard", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.include_router(operations_router)


@app.middleware("http")
async def authentication_and_headers(request: Request, call_next) -> Response:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    path = request.url.path
    public = path in PUBLIC_PATHS or path.startswith("/static/")
    session = read_session(request, settings.dashboard_session_secret)
    request.state.session = session

    if not public and session is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Autenticação necessária"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    if request.method not in {"GET", "HEAD", "OPTIONS"} and path != "/api/login":
        if session is None or not require_csrf(request, session):
            return JSONResponse({"detail": "Token CSRF inválido"}, status_code=403)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; manifest-src 'self'; worker-src 'self'; frame-ancestors 'none'"
    if path.startswith("/api/") or path in {"/health", "/settings"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/login", response_class=HTMLResponse, response_model=None)
async def login_page(request: Request) -> Response:
    settings = request.app.state.settings
    if read_session(request, settings.dashboard_session_secret):
        return RedirectResponse("/", status_code=303)
    return TEMPLATES.TemplateResponse(request=request, name="login.html", context={"title": settings.dashboard_title})


@app.post("/api/login")
async def login(body: LoginRequest, request: Request) -> Response:
    settings = request.app.state.settings
    if body.username != settings.dashboard_username or not verify_password(body.password, settings.dashboard_password):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    token = create_session(body.username, settings.dashboard_session_secret)
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=request.url.scheme == "https", samesite="strict", max_age=8 * 60 * 60, path="/")
    return response


@app.post("/api/logout")
async def logout() -> Response:
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    return TEMPLATES.TemplateResponse(request=request, name="index.html", context={"title": settings.dashboard_title, "version": APP_VERSION, "refresh_seconds": settings.refresh_seconds, "default_theme": settings.dashboard_default_theme, "csrf": request.state.session.csrf})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    return TEMPLATES.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "title": settings.dashboard_title,
            "version": APP_VERSION,
            "values": masked_settings(settings.dashboard_env_file),
            "pves": masked_pve_settings(settings.load_pve_instances()),
            "pbses": masked_pbs_settings(settings.load_pbs_instances()),
            "csrf": request.state.session.csrf,
            "default_theme": settings.dashboard_default_theme,
        },
    )


@app.put("/api/settings")
async def save_settings(body: SettingsUpdate, request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    try:
        write_env(settings.dashboard_env_file, body.values, body.pves, settings.load_pve_instances(), body.pbses, settings.load_pbs_instances())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao gravar ENV: {exc}") from exc
    asyncio.create_task(restart_after_settings_save())
    return {"ok": True, "restart_required": False, "restarting": True}


@app.get("/api/session")
async def session_info(request: Request) -> dict[str, str]:
    return {"username": request.state.session.username, "csrf": request.state.session.csrf}


@app.get("/api/dashboard", response_model=DashboardPayload)
async def dashboard(request: Request) -> DashboardPayload:
    try:
        return await request.app.state.service.get_dashboard()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/pve/{pve_id}/summary", response_model=PveSummary)
async def pve_summary(pve_id: str, request: Request) -> PveSummary:
    client = request.app.state.pve_clients.get(pve_id)
    if client is None:
        raise HTTPException(status_code=404, detail="PVE não encontrado")
    try:
        return await client.get_summary()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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


@app.get("/manifest.webmanifest")
async def manifest() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
async def service_worker() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    try:
        payload = await request.app.state.service.get_dashboard()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": all(source.ok for source in payload.pve) and all(source.ok for source in payload.pbs), "pve": [source.model_dump() for source in payload.pve], "pbs": [source.model_dump() for source in payload.pbs], "updated_at": payload.updated_at, "stale": payload.stale}
