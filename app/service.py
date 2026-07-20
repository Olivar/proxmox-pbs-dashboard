from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.models import BackupInfo, DashboardPayload, SourceHealth, VmInfo
from app.pbs import PbsClient
from app.proxmox import ProxmoxClient, ProxmoxError


class DashboardService:
    def __init__(self, settings: Settings, pve: list[ProxmoxClient], pbs: PbsClient) -> None:
        if not pve:
            raise ValueError("Ao menos uma instância PVE deve ser configurada")
        self.settings = settings
        self.pve = pve
        self.pbs = pbs
        self._lock = asyncio.Lock()
        self._cached: DashboardPayload | None = None
        self._expires_at: datetime | None = None

    async def get_dashboard(self, force: bool = False) -> DashboardPayload:
        now = datetime.now(UTC)
        if not force and self._cached and self._expires_at and now < self._expires_at:
            return self._cached

        async with self._lock:
            now = datetime.now(UTC)
            if not force and self._cached and self._expires_at and now < self._expires_at:
                return self._cached
            return await self._refresh(now)

    async def _refresh(self, now: datetime) -> DashboardPayload:
        results = await asyncio.gather(
            *(client.get_vms() for client in self.pve),
            self.pbs.get_backups(),
            return_exceptions=True,
        )
        pve_results = results[:-1]
        pbs_result = results[-1]

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
                pve_health.append(
                    SourceHealth(
                        ok=False,
                        source_id=client.instance.id,
                        source_name=client.instance.name,
                        error=error,
                    )
                )
                vms.extend(cached_by_source.get(client.instance.id, []))
                continue

            successful_sources += 1
            pve_health.append(
                SourceHealth(
                    ok=True,
                    source_id=client.instance.id,
                    source_name=client.instance.name,
                )
            )
            vms.extend(result)

        if successful_sources == 0 and not vms:
            raise ProxmoxError("; ".join(pve_errors) or "Nenhuma instância PVE respondeu")

        pbs_health = SourceHealth(ok=True, source_id="pbs", source_name="PBS")
        if isinstance(pbs_result, Exception):
            pbs_health = SourceHealth(
                ok=False,
                source_id="pbs",
                source_name="PBS",
                error=str(pbs_result),
            )
            backups = self._cached_backups()
        else:
            backups = pbs_result

        for vm in vms:
            vm.backup = backups.get(
                vm.vmid,
                BackupInfo(status="missing", detail="Nenhum snapshot localizado"),
            ).model_copy(deep=True)

        payload = DashboardPayload(
            title=self.settings.dashboard_title,
            updated_at=now,
            stale=any(not source.ok for source in pve_health) or not pbs_health.ok,
            vms=sorted(vms, key=lambda vm: (vm.pve_name.casefold(), vm.name.casefold(), vm.vmid)),
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
