from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import httpx

from app.config import PveInstance, Settings
from app.ip_cache import IpCache
from app.models import GuestActionRequest, VmInfo
from app.note_store import NoteStore
from app.utils import format_uptime, pick, state_display


class ProxmoxError(RuntimeError):
    pass


class ProxmoxClient:
    def __init__(self, settings: Settings, instance: PveInstance, ip_cache: IpCache, notes: NoteStore) -> None:
        self.settings = settings
        self.instance = instance
        self.ip_cache = ip_cache
        self.notes = notes
        self.client = httpx.AsyncClient(
            base_url=instance.base_url,
            timeout=settings.request_timeout_seconds,
            verify=instance.verify_tls,
            headers={
                "Authorization": f"PVEAPIToken={instance.token_id}={instance.token_secret}",
                "Accept": "application/json",
            },
        )
        self._agent_semaphore = asyncio.Semaphore(settings.max_parallel_guest_agent_requests)

    async def close(self) -> None:
        await self.client.aclose()

    async def get_vms(self) -> list[VmInfo]:
        data = await self._get_json("/api2/json/cluster/resources", params={"type": "vm"})
        if not isinstance(data, list):
            raise ProxmoxError(f"{self.instance.name}: PVE retornou uma lista de guests inválida")

        overrides = self.settings.load_ip_overrides()
        guests: list[VmInfo] = []
        pending_ip: list[tuple[VmInfo, asyncio.Task[str | None]]] = []

        for item in data:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type", "")).lower()
            if kind not in {"qemu", "lxc"} or int(item.get("template") or 0) == 1:
                continue
            try:
                vmid = int(item["vmid"])
            except (KeyError, TypeError, ValueError):
                continue

            node = str(item.get("node") or "")
            state, display = state_display(str(item.get("status") or ""))
            uptime = int(item.get("uptime") or 0) if state == "running" else 0
            fallback_ip = overrides.get(vmid) or self.ip_cache.get(vmid)
            guest = VmInfo(
                vmid=vmid,
                name=str(item.get("name") or f"Guest-{vmid}"),
                kind=kind,
                kind_display="VM" if kind == "qemu" else "CT",
                pve_id=self.instance.id,
                pve_name=self.instance.name,
                pve_url=self.instance.base_url,
                node=node,
                ip=fallback_ip,
                note=self.notes.get(self.instance.id, vmid),
                cpu_percent=percent(item.get("cpu"), scale=100),
                ram_percent=ratio_percent(item.get("mem"), item.get("maxmem")),
                uptime_seconds=max(0, uptime),
                uptime_display=format_uptime(uptime),
                state=state,
                state_display=display,
            )
            guests.append(guest)

            if state == "running" and node:
                resolver = self._get_qemu_ip(node, vmid) if kind == "qemu" else self._get_lxc_ip(node, vmid)
                pending_ip.append((guest, asyncio.create_task(resolver)))

        for guest, task in pending_ip:
            try:
                resolved_ip = await task
            except Exception:
                resolved_ip = None
            if resolved_ip:
                guest.ip = resolved_ip
                self.ip_cache.set(guest.vmid, resolved_ip)

        return sorted(guests, key=lambda guest: (guest.name.casefold(), guest.vmid))

    async def _get_qemu_ip(self, node: str, vmid: int) -> str | None:
        async with self._agent_semaphore:
            try:
                data = await self._get_json(f"/api2/json/nodes/{node}/qemu/{vmid}/agent/network-get-interfaces")
            except ProxmoxError:
                return None
        return select_guest_ip(data, self.settings.excluded_interfaces)

    async def _get_lxc_ip(self, node: str, vmid: int) -> str | None:
        async with self._agent_semaphore:
            try:
                data = await self._get_json(f"/api2/json/nodes/{node}/lxc/{vmid}/interfaces")
            except ProxmoxError:
                return None
        return select_guest_ip(data, self.settings.excluded_interfaces)

    async def operate_guest(
        self, node: str, kind: str, vmid: int, action: str, credentials: GuestActionRequest
    ) -> str | None:
        if kind not in {"qemu", "lxc"} or action not in {"start", "shutdown", "reboot"}:
            raise ProxmoxError("Operação de guest inválida")
        username = credentials.username.strip()
        realm = credentials.realm.strip()
        if "@" not in username:
            username = f"{username}@{realm}"
        auth_data: dict[str, str] = {"username": username, "password": credentials.password}
        if credentials.otp and credentials.otp.strip():
            auth_data["otp"] = credentials.otp.strip()
        try:
            async with httpx.AsyncClient(
                base_url=self.instance.base_url,
                timeout=self.settings.request_timeout_seconds,
                verify=self.instance.verify_tls,
                headers={"Accept": "application/json"},
            ) as client:
                auth = await client.post("/api2/json/access/ticket", data=auth_data)
                auth.raise_for_status()
                payload = auth.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, dict) or not data.get("ticket"):
                    raise ProxmoxError("Autenticação recusada pelo PVE")
                headers = {"CSRFPreventionToken": str(data.get("CSRFPreventionToken") or "")}
                cookies = {"PVEAuthCookie": str(data["ticket"])}
                response = await client.post(
                    f"/api2/json/nodes/{node}/{kind}/{vmid}/status/{action}",
                    headers=headers,
                    cookies=cookies,
                )
                response.raise_for_status()
                result = response.json()
        except ProxmoxError:
            raise
        except (httpx.HTTPStatusError, httpx.RequestError, ValueError) as exc:
            detail = ""
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    error_payload = exc.response.json()
                    detail = str(error_payload.get("errors") or error_payload.get("data") or "")
                except ValueError:
                    detail = exc.response.text[:300]
            suffix = f": {detail}" if detail else ""
            raise ProxmoxError(f"Falha na operação em {self.instance.name}{suffix}") from exc
        if not isinstance(result, dict) or "data" not in result:
            raise ProxmoxError(f"Resposta inválida da API {self.instance.name}")
        return str(result["data"]) if result["data"] else None

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self.client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProxmoxError(f"Falha ao consultar {self.instance.name}: {exc}") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise ProxmoxError(f"Resposta inválida da API {self.instance.name}")
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
        name = str(pick(interface, "name", "interface", "ifname", default="")).lower()
        if any(name.startswith(prefix) for prefix in excluded_prefixes):
            continue
        addresses = pick(interface, "ip-addresses", "ip_addresses", "addresses", default=[])
        if not isinstance(addresses, list) or not addresses:
            raw_inet = pick(interface, "inet", "ip", default=None)
            addresses = [{"address": raw_inet.split("/", 1)[0]}] if isinstance(raw_inet, str) else []
        for address in addresses:
            if not isinstance(address, dict):
                continue
            raw_ip = pick(address, "ip-address", "ip_address", "address")
            if not isinstance(raw_ip, str):
                continue
            try:
                ip = ipaddress.ip_address(raw_ip.split("%", 1)[0].split("/", 1)[0])
            except ValueError:
                continue
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                continue
            priority = 0 if isinstance(ip, ipaddress.IPv4Address) and ip.is_private else 1
            if isinstance(ip, ipaddress.IPv6Address):
                priority += 2
            candidates.append((priority, str(ip)))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], ipaddress.ip_address(item[1])))
    return candidates[0][1]


def percent(value: Any, scale: int = 1) -> int:
    try:
        return max(0, min(100, round(float(value or 0) * scale)))
    except (TypeError, ValueError):
        return 0


def ratio_percent(value: Any, maximum: Any) -> int:
    try:
        total = float(maximum or 0)
        return 0 if total <= 0 else max(0, min(100, round(float(value or 0) / total * 100)))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
