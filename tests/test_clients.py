from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import PbsInstance, PveInstance, Settings
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
                        "disk": 30 * 1024**3,
                        "maxdisk": 60 * 1024**3,
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
    assert vms[0].disk_percent == 50
    assert vms[0].disk_total_bytes == 60 * 1024**3
    assert vms[0].pve_name == "PVE"
    assert vms[0].ip == "192.168.10.20"
    assert vms[0].uptime_display == "1d 01h 01m"
    assert vms[0].state_display == "Ligado"


@pytest.mark.asyncio
async def test_pve_client_collects_node_summary(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    instance = PveInstance(
        id="pve01",
        name="PVE Principal",
        url="https://pve.test:8006",
        token_id="dashboard@pve!readonly",
        token_secret="pve-secret",
        verify_tls=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "PVEAPIToken=dashboard@pve!readonly=pve-secret"
        if request.url.path == "/api2/json/nodes":
            return httpx.Response(200, json={"data": [
                {
                    "node": "pve01",
                    "status": "online",
                    "cpu": 0.25,
                    "maxcpu": 4,
                    "mem": 4 * 1024**3,
                    "maxmem": 8 * 1024**3,
                    "disk": 20 * 1024**3,
                    "maxdisk": 40 * 1024**3,
                    "uptime": 90061,
                    "loadavg": ["0.50", "0.20", "0.10"],
                }
            ]})
        if request.url.path.endswith("/tasks"):
            return httpx.Response(200, json={"data": [{
                "type": "vzdump",
                "id": "100",
                "upid": "UPID:pve01:1",
                "status": "stopped",
                "starttime": 1_784_429_200,
                "endtime": 1_784_429_500,
            }]})
        return httpx.Response(404)

    client = ProxmoxClient(settings, instance, IpCache(settings.ip_cache_file))
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        base_url=instance.base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "PVEAPIToken=dashboard@pve!readonly=pve-secret"},
    )
    try:
        summary = await client.get_summary()
    finally:
        await client.close()

    assert summary.cpu_percent == 25
    assert summary.ram_percent == 50
    assert summary.disk_percent == 50
    assert summary.cpu_total_cores == 4
    assert summary.nodes[0].load_average == 0.5
    assert len(summary.tasks) == 1
    assert summary.tasks[0].node == "pve01"
    assert summary.tasks[0].task_type == "vzdump"
    assert summary.tasks[0].description == "Backup Job"
    assert summary.tasks[0].status == "stopped"


@pytest.mark.asyncio
async def test_pve_client_collects_live_guest_metrics(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    instance = PveInstance(
        id="pve01",
        name="PVE Principal",
        url="https://pve.test:8006",
        token_id="token",
        token_secret="secret",
        verify_tls=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status/current"):
            return httpx.Response(200, json={"data": {
                "cpu": 0.35,
                "mem": 6 * 1024**3,
                "maxmem": 8 * 1024**3,
                "disk": 0,
                "maxdisk": 0,
                "netin": 10_000,
                "netout": 20_000,
            }})
        if request.url.path.endswith("/config"):
            return httpx.Response(200, json={"data": {"net0": "virtio=AA:BB:CC:DD:EE:FF,rate=100"}})
        if request.url.path.endswith("/cluster/resources"):
            return httpx.Response(200, json={"data": [{"type": "qemu", "vmid": 100, "node": "pve01", "disk": 30 * 1024**3, "maxdisk": 60 * 1024**3}]})
        if request.url.path.endswith("/agent/get-fsinfo"):
            return httpx.Response(200, json={"data": {"result": [{"total-bytes": 60 * 1024**3, "used-bytes": 30 * 1024**3}]}})
        return httpx.Response(404)

    client = ProxmoxClient(settings, instance, IpCache(settings.ip_cache_file))
    await client.client.aclose()
    client.client = httpx.AsyncClient(base_url=instance.base_url, transport=httpx.MockTransport(handler))
    try:
        metrics = await client.get_guest_metrics("pve01", "qemu", 100)
    finally:
        await client.close()

    assert metrics.cpu_percent == 35
    assert metrics.ram_percent == 75
    assert metrics.disk_percent == 50
    assert metrics.network_limit_bps == 100_000_000
    assert metrics.network_in_bytes == 10_000
    assert metrics.network_out_bytes == 20_000


@pytest.mark.asyncio
async def test_pve_client_operates_guest_with_console_ticket(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    instance = PveInstance(id="pve", name="PVE", url="https://pve.test:8006", token_id="token", token_secret="secret", verify_tls=False)
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["csrf"] = request.headers.get("CSRFPreventionToken", "")
        observed["cookie"] = request.headers.get("Cookie", "")
        return httpx.Response(200, json={"data": "UPID:pve:1"})

    client = ProxmoxClient(settings, instance, IpCache(settings.ip_cache_file))
    await client.client.aclose()
    client.client = httpx.AsyncClient(base_url=instance.base_url, transport=httpx.MockTransport(handler))
    try:
        upid = await client.operate_guest_with_ticket("node-a", "qemu", 100, "reboot", "auth-ticket", "csrf-token")
    finally:
        await client.close()

    assert upid == "UPID:pve:1"
    assert observed == {"csrf": "csrf-token", "cookie": "PVEAuthCookie=auth-ticket"}


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


@pytest.mark.asyncio
async def test_pbs_client_collects_summary_and_jobs(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    instance = PbsInstance(
        id="pbs",
        name="PBS",
        url="https://pbs.test:8007",
        token_id="dashboard@pbs!readonly",
        token_secret="pbs-secret",
        datastores="store",
        node="localhost",
        verify_tls=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/status") and "/datastore/" not in request.url.path:
            return httpx.Response(200, json={"data": {
                "cpu": 0.25,
                "cpus": 8,
                "memory": {"used": 6 * 1024**3, "total": 8 * 1024**3},
                "root": {"used": 20 * 1024**3, "total": 40 * 1024**3},
            }})
        if request.url.path.endswith("/tasks"):
            return httpx.Response(200, json={"data": [{
                "worker-type": "verify",
                "worker-id": "store:vm/100",
                "upid": "UPID:pbs:1",
                "status": "OK",
                "starttime": 1_784_429_200,
                "endtime": 1_784_429_500,
            }]})
        if request.url.path.endswith("/admin/datastore/store/status"):
            return httpx.Response(200, json={"data": {
                "used": 30 * 1024**3,
                "total": 100 * 1024**3,
                "avail": 70 * 1024**3,
            }})
        return httpx.Response(404)

    client = PbsClient(settings, instance)
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        base_url=instance.base_url,
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "PBSAPIToken dashboard@pbs!readonly:pbs-secret"},
    )
    try:
        summary = await client.get_summary()
    finally:
        await client.close()

    assert summary.status == "online"
    assert summary.cpu_percent == 25
    assert summary.ram_percent == 75
    assert summary.disk_percent == 30
    assert summary.datastores[0].name == "store"
    assert summary.tasks[0].description == "Verification job"
