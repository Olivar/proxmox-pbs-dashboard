from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.models import BackupInfo, DashboardPayload, SourceHealth
from app.pbs import PbsClient
from app.proxmox import ProxmoxClient, ProxmoxError


class DashboardService:
    def __init__(self, settings: Settings, pve: ProxmoxClient, pbs: PbsClient) -> None:
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
        pve_result, pbs_result = await asyncio.gather(
            self.pve.get_vms(),
            self.pbs.get_backups(),
            return_exceptions=True,
        )

        pve_health = SourceHealth(ok=True)
        pbs_health = SourceHealth(ok=True)

        if isinstance(pve_result, Exception):
            pve_health = SourceHealth(ok=False, error=str(pve_result))
            if self._cached:
                stale = self._cached.model_copy(deep=True)
                stale.updated_at = now
                stale.stale = True
                stale.pve = pve_health
                if isinstance(pbs_result, Exception):
                    stale.pbs = SourceHealth(ok=False, error=str(pbs_result))
                self._cached = stale
                self._expires_at = now + timedelta(seconds=self.settings.refresh_seconds)
                return stale
            raise ProxmoxError(str(pve_result))

        if isinstance(pbs_result, Exception):
            pbs_health = SourceHealth(ok=False, error=str(pbs_result))
            backups: dict[int, BackupInfo] = {}
        else:
            backups = pbs_result

        for vm in pve_result:
            vm.backup = backups.get(vm.vmid, BackupInfo(status="missing", detail="Nenhum snapshot localizado"))

        payload = DashboardPayload(
            title=self.settings.dashboard_title,
            updated_at=now,
            stale=False,
            vms=pve_result,
            pve=pve_health,
            pbs=pbs_health,
        )
        self._cached = payload
        self._expires_at = now + timedelta(seconds=self.settings.refresh_seconds)
        return payload
