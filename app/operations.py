from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models import GuestActionRequest, GuestActionResponse

router = APIRouter(prefix="/api/guests")


@router.post("/{pve_id}/{node}/{kind}/{vmid}/{action}", response_model=GuestActionResponse)
async def guest_action(
    pve_id: str,
    node: str,
    kind: str,
    vmid: int,
    action: str,
    body: GuestActionRequest,
    request: Request,
) -> GuestActionResponse:
    client = request.app.state.pve_clients.get(pve_id)
    if client is None:
        raise HTTPException(status_code=404, detail="PVE não encontrado")
    try:
        upid = await client.operate_guest(node, kind, vmid, action, body)
        await request.app.state.service.get_dashboard(force=True)
        return GuestActionResponse(action=action, upid=upid)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
