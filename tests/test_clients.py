from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.ip_cache import IpCache
from app.pbs import PbsClient
from app.proxmox import ProxmoxClient


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        pve_url="https://pve.test:8006",
        pve_token_id="dashboard@pve!readonly",
        pve_token_secret="pve-secret",
        pve_verify_tls=False,
        pbs_url="https://pbs.test:8007",
        pbs_token_id="dashboard@pbs!readonly",
        pbs_token_secret="pbs-secret",
        pbs_datastores="store",
        pbs_verify_tls=False,
        ip_cache_file=tmp_path / "ip-cache.json",
        ip_overrides_file=tmp_path / "ip-overrides.json",
    )


@pytest.mark.asyncio
async def test_pve_client_collects_vm_and_guest_ip(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "PVEAPIToken=dashboard@pve!readonly=pve-secret"
        if request.url.path == "/api2/json/cluster/resources":
            return httpx.Response(200, json={"data": [
                {
                    "type": "qemu",
                    "vmid": 100,
                    "name": "SRV-ERP",
                    "node": "pve01",
                    "status": "running",
                    "uptime": 90061,
                }
            ]})
        if request.url.path.endswith("/agent/network-get-interfaces"):
            return httpx.Response(200, json={"data": {"result": [
                {
                    "name": "eth0",
                    "ip-addresses": [
                        {"ip-address": "192.168.10.20", "ip-address-type": "ipv4"}
                    ],
                }
            ]}})
        return httpx.Response(404)

    instance = settings.load_pve_instances()[0]
    client = ProxmoxClient(settings, instance, IpCache(settings.ip_cache_file))
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        base_url=instance.base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "PVEAPIToken=dashboard@pve!readonly=pve-secret"},
    )
    try:
        vms = await client.get_vms()
    finally:
        await client.close()

    assert len(vms) == 1
    assert vms[0].name == "SRV-ERP"
    assert vms[0].pve_id == "pve"
    assert vms[0].pve_name == "PVE"
    assert vms[0].ip == "192.168.10.20"
    assert vms[0].uptime_display == "1d 01h 01m"
    assert vms[0].state_display == "Ligado"


@pytest.mark.asyncio
async def test_pbs_client_merges_snapshot_and_newer_failed_task(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "PBSAPIToken dashboard@pbs!readonly:pbs-secret"
        if request.url.path.endswith("/snapshots"):
            return httpx.Response(200, json={"data": [
                {
                    "backup-type": "vm",
                    "backup-id": "100",
                    "backup-time": 1_784_425_600,
                }
            ]})
        if request.url.path.endswith("/tasks"):
            return httpx.Response(200, json={"data": [
                {
                    "worker-type": "backup",
                    "worker-id": "store:vm/100/2026-07-20T03:00:00Z",
                    "starttime": 1_784_429_200,
                    "endtime": 1_784_429_500,
                    "status": "TASK ERROR: connection reset",
                }
            ]})
        return httpx.Response(404)

    client = PbsClient(settings)
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        base_url=settings.pbs_base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "PBSAPIToken dashboard@pbs!readonly:pbs-secret"},
    )
    try:
        backups = await client.get_backups()
    finally:
        await client.close()

    assert backups[100].datastore == "store"
    assert backups[100].last_backup is not None
    assert backups[100].status == "failed"
