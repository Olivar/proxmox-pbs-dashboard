from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

GuestState = Literal["running", "stopped", "unknown"]
GuestKind = Literal["qemu", "lxc"]
BackupStatus = Literal["success", "failed", "running", "missing", "unknown"]


class BackupInfo(BaseModel):
    datastore: str | None = None
    last_backup: datetime | None = None
    status: BackupStatus = "missing"
    detail: str | None = None


class VmInfo(BaseModel):
    vmid: int
    name: str
    kind: GuestKind = "qemu"
    kind_display: str = "VM"
    pve_id: str
    pve_name: str
    pve_url: str
    node: str
    ip: str | None = None
    note: str = ""
    uptime_seconds: int = Field(default=0, ge=0)
    uptime_display: str = "—"
    state: GuestState = "unknown"
    state_display: str = "Desconhecido"
    backup: BackupInfo = Field(default_factory=BackupInfo)


class SourceHealth(BaseModel):
    ok: bool
    source_id: str | None = None
    source_name: str | None = None
    error: str | None = None


class DashboardPayload(BaseModel):
    title: str
    updated_at: datetime
    stale: bool = False
    vms: list[VmInfo]
    pve: list[SourceHealth]
    pbs: SourceHealth


class NoteUpdate(BaseModel):
    note: str = Field(default="", max_length=4000)
