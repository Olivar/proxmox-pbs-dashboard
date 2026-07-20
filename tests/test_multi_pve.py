from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config import PveInstance, Settings
from app.models import BackupInfo, VmInfo
from app.service import DashboardService


def make_settings(tmp_path: Path, instances_file: Path) -> Settings:
    return Settings(
        pve_instances_file=instances_file,
        pbs_url="https://pbs.test:8007",
        pbs_token_id="dashboard@pbs!readonly",
        pbs_token_secret="pbs-secret",
        pbs_datastores="store",
        pbs_verify_tls=False,
        ip_cache_file=tmp_path / "ip-cache.json",
        ip_overrides_file=tmp_path / "ip-overrides.json",
    )


def test_loads_multiple_pve_instances(tmp_path: Path) -> None:
    instances_file = tmp_path / "pve-instances.json"
    instances_file.write_text(json.dumps([
        {
            "id": "pve01",
            "name": "PVE Principal",
            "url": "https://pve01.test:8006",
            "token_id": "dashboard@pve!readonly",
            "token_secret": "secret-1",
            "verify_tls": False,
        },
        {
            "id": "pve02",
            "name": "PVE Filial",
            "url": "https://pve02.test:8006",
            "token_id": "dashboard@pve!readonly",
            "token_secret": "secret-2",
            "verify_tls": False,
        },
    ]), encoding="utf-8")

    instances = make_settings(tmp_path, instances_file).load_pve_instances()

    assert [instance.id for instance in instances] == ["pve01", "pve02"]
    assert instances[1].name == "PVE Filial"
    assert instances[1].base_url == "https://pve02.test:8006"


def test_rejects_duplicate_pve_ids(tmp_path: Path) -> None:
    instances_file = tmp_path / "pve-instances.json"
    instances_file.write_text(json.dumps([
        {
            "id": "pve01",
            "name": "PVE 1",
            "url": "https://pve01.test:8006",
            "token_id": "token",
            "token_secret": "secret",
        },
        {
            "id": "PVE01",
            "name": "PVE 2",
            "url": "https://pve02.test:8006",
            "token_id": "token",
            "token_secret": "secret",
        },
    ]), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicado"):
        make_settings(tmp_path, instances_file).load_pve_instances()


class FakePveClient:
    def __init__(self, instance: PveInstance, vms: list[VmInfo] | Exception) -> None:
        self.instance = instance
        self._vms = vms

    async def get_vms(self) -> list[VmInfo]:
        if isinstance(self._vms, Exception):
            raise self._vms
        return [vm.model_copy(deep=True) for vm in self._vms]


class FakePbsClient:
    async def get_backups(self) -> dict[int, BackupInfo]:
        return {
            100: BackupInfo(
                datastore="store",
                last_backup=datetime(2026, 7, 20, 2, tzinfo=UTC),
                status="success",
            ),
            200: BackupInfo(
                datastore="store",
                last_backup=datetime(2026, 7, 20, 3, tzinfo=UTC),
                status="success",
            ),
        }


@pytest.mark.asyncio
async def test_service_aggregates_independent_pve_instances(tmp_path: Path) -> None:
    settings = Settings(
        pve_url="https://legacy.test:8006",
        pve_token_id="token",
        pve_token_secret="secret",
        pve_instances_file=tmp_path / "missing.json",
        pbs_url="https://pbs.test:8007",
        pbs_token_id="pbs-token",
        pbs_token_secret="pbs-secret",
        pbs_datastores="store",
    )
    pve01 = PveInstance(
        id="pve01",
        name="PVE Principal",
        url="https://pve01.test:8006",
        token_id="token",
        token_secret="secret",
    )
    pve02 = PveInstance(
        id="pve02",
        name="PVE Filial",
        url="https://pve02.test:8006",
        token_id="token",
        token_secret="secret",
    )
    clients = [
        FakePveClient(pve01, [VmInfo(
            vmid=100,
            name="SRV-ERP",
            pve_id="pve01",
            pve_name="PVE Principal",
            node="pve01",
            state="running",
            state_display="Ligado",
        )]),
        FakePveClient(pve02, [VmInfo(
            vmid=200,
            name="SRV-AD",
            pve_id="pve02",
            pve_name="PVE Filial",
            node="pve02",
            state="stopped",
            state_display="Desligado",
        )]),
    ]

    service = DashboardService(settings, clients, FakePbsClient())  # type: ignore[arg-type]
    payload = await service.get_dashboard(force=True)

    assert [vm.vmid for vm in payload.vms] == [200, 100]
    assert {vm.vmid: vm.backup.status for vm in payload.vms} == {100: "success", 200: "success"}
    assert [source.source_id for source in payload.pve] == ["pve01", "pve02"]
    assert all(source.ok for source in payload.pve)
