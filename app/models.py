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
    pve_url: str = ""
    node: str
    ip: str | None = None
    note: str = ""
    cpu_percent: int = Field(default=0, ge=0, le=100)
    cpu_total_cores: float = Field(default=0, ge=0)
    ram_percent: int = Field(default=0, ge=0, le=100)
    ram_total_bytes: int = Field(default=0, ge=0)
    disk_percent: int | None = Field(default=None, ge=0, le=100)
    disk_used_bytes: int = Field(default=0, ge=0)
    disk_total_bytes: int = Field(default=0, ge=0)
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


class PveNodeSummary(BaseModel):
    node: str
    status: str = "unknown"
    cpu_percent: int = Field(default=0, ge=0, le=100)
    cpu_total_cores: int = Field(default=0, ge=0)
    ram_percent: int = Field(default=0, ge=0, le=100)
    ram_used_bytes: int = Field(default=0, ge=0)
    ram_total_bytes: int = Field(default=0, ge=0)
    disk_percent: int = Field(default=0, ge=0, le=100)
    disk_used_bytes: int = Field(default=0, ge=0)
    disk_total_bytes: int = Field(default=0, ge=0)
    uptime_seconds: int = Field(default=0, ge=0)
    uptime_display: str = "â€”"
    load_average: float | None = Field(default=None, ge=0)


class PveTaskSummary(BaseModel):
    node: str
    task_type: str = "unknown"
    task_id: str | None = None
    description: str = "Unknown task"
    status: str = "unknown"
    start_at: datetime | None = None
    end_at: datetime | None = None
    upid: str | None = None


class PveSummary(BaseModel):
    pve_id: str
    pve_name: str
    pve_url: str
    updated_at: datetime
    node_count: int = Field(default=0, ge=0)
    online_node_count: int = Field(default=0, ge=0)
    cpu_percent: int = Field(default=0, ge=0, le=100)
    cpu_total_cores: int = Field(default=0, ge=0)
    ram_percent: int = Field(default=0, ge=0, le=100)
    ram_used_bytes: int = Field(default=0, ge=0)
    ram_total_bytes: int = Field(default=0, ge=0)
    disk_percent: int = Field(default=0, ge=0, le=100)
    disk_used_bytes: int = Field(default=0, ge=0)
    disk_total_bytes: int = Field(default=0, ge=0)
    nodes: list[PveNodeSummary] = Field(default_factory=list)
    tasks: list[PveTaskSummary] = Field(default_factory=list)


class PbsDatastoreSummary(BaseModel):
    name: str
    status: str = "unknown"
    used_bytes: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    avail_bytes: int = Field(default=0, ge=0)
    percent: int = Field(default=0, ge=0, le=100)


class PbsTaskSummary(BaseModel):
    task_type: str = "unknown"
    task_id: str | None = None
    description: str = "Unknown task"
    status: str = "unknown"
    start_at: datetime | None = None
    end_at: datetime | None = None
    upid: str | None = None


class PbsSummary(BaseModel):
    pbs_id: str
    pbs_name: str
    pbs_url: str
    updated_at: datetime
    node: str
    status: str = "unknown"
    cpu_percent: int = Field(default=0, ge=0, le=100)
    cpu_total_cores: int = Field(default=0, ge=0)
    ram_percent: int = Field(default=0, ge=0, le=100)
    ram_used_bytes: int = Field(default=0, ge=0)
    ram_total_bytes: int = Field(default=0, ge=0)
    disk_percent: int = Field(default=0, ge=0, le=100)
    disk_used_bytes: int = Field(default=0, ge=0)
    disk_total_bytes: int = Field(default=0, ge=0)
    datastores: list[PbsDatastoreSummary] = Field(default_factory=list)
    tasks: list[PbsTaskSummary] = Field(default_factory=list)


class GuestLiveMetrics(BaseModel):
    pve_id: str
    node: str
    vmid: int
    updated_at: datetime
    cpu_percent: int | None = Field(default=None, ge=0, le=100)
    ram_percent: int | None = Field(default=None, ge=0, le=100)
    ram_used_bytes: int = Field(default=0, ge=0)
    ram_total_bytes: int = Field(default=0, ge=0)
    disk_percent: int | None = Field(default=None, ge=0, le=100)
    disk_used_bytes: int = Field(default=0, ge=0)
    disk_total_bytes: int = Field(default=0, ge=0)
    network_percent: int | None = Field(default=None, ge=0, le=100)
    network_limit_bps: int | None = Field(default=None, ge=0)
    network_in_bytes: int = Field(default=0, ge=0)
    network_out_bytes: int = Field(default=0, ge=0)


class DashboardPayload(BaseModel):
    title: str
    updated_at: datetime
    stale: bool = False
    vms: list[VmInfo]
    pve: list[SourceHealth]
    pbs: list[SourceHealth]


class NoteUpdate(BaseModel):
    note: str = Field(default="", max_length=4000)


class GuestActionRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    realm: str = Field(default="pam", min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)
    otp: str | None = Field(default=None, max_length=256)


class GuestActionResponse(BaseModel):
    ok: bool = True
    action: Literal["start", "shutdown", "reboot"]
    upid: str | None = None
