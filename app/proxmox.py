from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import httpx

from app.config import Settings
from app.ip_cache import IpCache
from app.models import VmInfo
from app.utils import format_uptime, pick, state_display


class ProxmoxError(RuntimeError):
    pass


class ProxmoxClient:
    def __init__(self, settings: Settings, ip_cache: IpCache) -> None:
        self.settings = settings
        self.ip_cache = ip_cache
        self.client = httpx.AsyncClient(
            base_url=settings.pve_base_url,
            timeout=settings.request_timeout_seconds,
            verify=settings.pve_verify_tls,
            headers={
                "Authorization": f"PVEAPIToken={settings.pve_token_id}={settings.pve_token_secret}",
                "Accept": "application/json",
            },
        )
        self._agent_semaphore = asyncio.Semaphore(settings.max_parallel_guest_agent_requests)

    async def close(self) -> None:
        await self.client.aclose()

    async def get_vms(self) -> list[VmInfo]:
        data = await self._get_json("/api2/json/cluster/resources", params={"type": "vm"})
        if not isinstance(data, list):
            raise ProxmoxError("PVE retornou uma lista de VMs inválida")

        overrides = self.settings.load_ip_overrides()
        vms: list[VmInfo] = []
        pending_ip: list[tuple[VmInfo, asyncio.Task[str | None]]] = []

        for item in data:
            if not isinstance(item, dict):
                continue
            if str(item.get("type", "")).lower() != "qemu":
                continue
            if int(item.get("template") or 0) == 1:
                continue

            try:
                vmid = int(item["vmid"])
            except (KeyError, TypeError, ValueError):
                continue

            node = str(item.get("node") or "")
            state, display = state_display(str(item.get("status") or ""))
            uptime = int(item.get("uptime") or 0) if state == "running" else 0
            fallback_ip = overrides.get(vmid) or self.ip_cache.get(vmid)
            vm = VmInfo(
                vmid=vmid,
                name=str(item.get("name") or f"VM-{vmid}"),
                node=node,
                ip=fallback_ip,
                uptime_seconds=max(0, uptime),
                uptime_display=format_uptime(uptime),
                state=state,
                state_display=display,
            )
            vms.append(vm)

            if state == "running" and node:
                pending_ip.append((vm, asyncio.create_task(self._get_guest_ip(node, vmid))))

        for vm, task in pending_ip:
            try:
                resolved_ip = await task
            except Exception:
                resolved_ip = None
            if resolved_ip:
                vm.ip = resolved_ip
                self.ip_cache.set(vm.vmid, resolved_ip)

        return sorted(vms, key=lambda vm: (vm.name.casefold(), vm.vmid))

    async def _get_guest_ip(self, node: str, vmid: int) -> str | None:
        async with self._agent_semaphore:
            try:
                data = await self._get_json(
                    f"/api2/json/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces"
                )
            except ProxmoxError:
                return None
        return select_guest_ip(data, self.settings.excluded_interfaces)

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self.client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProxmoxError(f"Falha ao consultar PVE: {exc}") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise ProxmoxError("Resposta inválida da API PVE")
        return payload["data"]


def select_guest_ip(data: Any, excluded_prefixes: tuple[str, ...]) -> str | None:
    interfaces = data
    if isinstance(data, dict):
        interfaces = pick(data, "result", "interfaces", default=[])
    if not isinstance(interfaces, list):
        return None

    candidates: list[tuple[int, str]] = []
    for interface in interfaces:
        if not isinstance(interface, dict):
            continue
        name = str(pick(interface, "name", "interface", default="")).lower()
        if any(name.startswith(prefix) for prefix in excluded_prefixes):
            continue
        addresses = pick(interface, "ip-addresses", "ip_addresses", "addresses", default=[])
        if not isinstance(addresses, list):
            continue
        for address in addresses:
            if not isinstance(address, dict):
                continue
            raw_ip = pick(address, "ip-address", "ip_address", "address")
            if not isinstance(raw_ip, str):
                continue
            try:
                ip = ipaddress.ip_address(raw_ip.split("%", 1)[0])
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                continue
            if isinstance(ip, ipaddress.IPv4Address):
                priority = 0 if ip.is_private else 1
            else:
                priority = 2 if ip.is_private else 3
            candidates.append((priority, str(ip)))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], ipaddress.ip_address(item[1])))
    return candidates[0][1]
