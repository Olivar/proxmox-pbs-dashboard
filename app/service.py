from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.models import BackupInfo, DashboardPayload, SourceHealth, VmInfo
from app.pbs import PbsClient
from app.proxmox import ProxmoxClient, ProxmoxError


class DashboardService:
    def __init__(self, settings: Settings, pve: list[ProxmoxClient], pbs: PbsClient | list[PbsClient]) -> None:
        if not pve:
            raise ValueError("Ao menos uma instância PVE deve ser configurada")
        pbs_clients = pbs if isinstance(pbs, list) else [pbs]
        if not pbs_clients:
            raise ValueError("Ao menos uma instÃ¢ncia PBS deve ser configurada")
        self.settings = settings
        self.pve = pve
        self.pbs = pbs_clients
        self._lock = asyncio.Lock()
        self._cached: DashboardPayload | None = None
        self._expires_at: datetime | None = None

    async def get_dashboard(self, force: bool = False) -> DashboardPayload:
        now = datetime.now(timezone.utc)
        if not force and self._cached and self._expires_at and now < self._expires_at:
            return self._cached
        async with self._lock:
            now = datetime.now(timezone.utc)
            if not force and self._cached and self._expires_at and now < self._expires_at:
                return self._cached
            return await self._refresh(now)

    async def _refresh(self, now: datetime) -> DashboardPayload:
        results = await asyncio.gather(*(client.get_vms() for client in self.pve), *(client.get_backups() for client in self.pbs), return_exceptions=True)
        pve_results, pbs_results = results[:len(self.pve)], results[len(self.pve):]
        cached_by_source: dict[str, list[VmInfo]] = {}
        if self._cached:
            for vm in self._cached.vms:
                cached_by_source.setdefault(vm.pve_id, []).append(vm.model_copy(deep=True))
        vms: list[VmInfo] = []
        pve_health: list[SourceHealth] = []
        pve_errors: list[str] = []
        successful_sources = 0
        for client, result in zip(self.pve, pve_results, strict=True):
            if isinstance(result, Exception):
                error = str(result)
                pve_errors.append(error)
                pve_health.append(SourceHealth(ok=False, source_id=client.instance.id, source_name=client.instance.name, error=error))
                vms.extend(cached_by_source.get(client.instance.id, []))
                continue
            successful_sources += 1
            pve_health.append(SourceHealth(ok=True, source_id=client.instance.id, source_name=client.instance.name))
            vms.extend(result)
        if successful_sources == 0 and not vms:
            raise ProxmoxError("; ".join(pve_errors) or "Nenhuma instância PVE respondeu")
        pbs_health: list[SourceHealth] = []
        backup_results: list[dict[int, BackupInfo]] = []
        pbs_errors: list[str] = []
        for client, result in zip(self.pbs, pbs_results, strict=True):
            instance = getattr(client, "instance", None)
            source_id = instance.id if instance else "pbs"
            source_name = instance.name if instance else "PBS"
            if isinstance(result, Exception):
                error = str(result)
                pbs_errors.append(error)
                pbs_health.append(SourceHealth(ok=False, source_id=source_id, source_name=source_name, error=error))
            else:
                pbs_health.append(SourceHealth(ok=True, source_id=source_id, source_name=source_name))
                backup_results.append(result)
        backups = merge_backup_results(backup_results) if backup_results else self._cached_backups()
        pbs_unavailable = not backup_results
        unavailable_detail = "PBS indisponível: " + "; ".join(pbs_errors) if pbs_errors else "PBS indisponível"
        for vm in vms:
            default_backup = (
                BackupInfo(status="unknown", detail=unavailable_detail)
                if pbs_unavailable and vm.vmid not in backups
                else BackupInfo(status="missing", detail="Nenhum snapshot localizado")
            )
            vm.backup = backups.get(vm.vmid, default_backup).model_copy(deep=True)
        payload = DashboardPayload(
            title=self.settings.dashboard_title,
            updated_at=now,
            stale=any(not source.ok for source in pve_health) or any(not source.ok for source in pbs_health),
            vms=sorted(vms, key=lambda vm: (vm.pve_name.casefold(), vm.kind, vm.name.casefold(), vm.vmid)),
            pve=pve_health,
            pbs=pbs_health,
        )
        self._cached = payload
        self._expires_at = now + timedelta(seconds=self.settings.refresh_seconds)
        return payload

    def _cached_backups(self) -> dict[int, BackupInfo]:
        if not self._cached:
            return {}
        return {vm.vmid: vm.backup.model_copy(deep=True) for vm in self._cached.vms}


def merge_backup_results(results: list[dict[int, BackupInfo]]) -> dict[int, BackupInfo]:
    merged: dict[int, BackupInfo] = {}
    for result in results:
        for vmid, backup in result.items():
            current = merged.get(vmid)
            if current is None or (backup.last_backup is not None and (current.last_backup is None or backup.last_backup > current.last_backup)):
                merged[vmid] = backup.model_copy(deep=True)
    return merged
