from __future__ import annotations

import asyncio
import ssl
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect


@dataclass(slots=True)
class ConsoleProxy:
    pve_url: str
    node: str
    vmid: int
    port: int
    vnc_ticket: str
    auth_ticket: str
    verify_tls: bool
    pve_id: str = ""
    csrf_token: str = ""

    @property
    def websocket_url(self) -> str:
        parsed = urlsplit(self.pve_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"/api2/json/nodes/{quote(self.node, safe='')}/qemu/{self.vmid}/vncwebsocket"
        query = urlencode({"port": self.port, "vncticket": self.vnc_ticket})
        return urlunsplit((scheme, parsed.netloc, path, query, ""))


@dataclass(slots=True)
class ConsoleSession:
    proxy: ConsoleProxy
    expires_at: float


class ConsoleSessionStore:
    def __init__(self, ttl_seconds: int = 90, active_ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self.active_ttl_seconds = active_ttl_seconds
        self._items: dict[str, ConsoleSession] = {}
        self._active: dict[str, ConsoleSession] = {}
        self._lock = asyncio.Lock()

    async def put(self, session_id: str, proxy: ConsoleProxy) -> None:
        async with self._lock:
            self._items[session_id] = ConsoleSession(proxy=proxy, expires_at=time.monotonic() + self.ttl_seconds)

    async def take(self, session_id: str) -> ConsoleProxy | None:
        async with self._lock:
            item = self._items.pop(session_id, None)
        if item is None or item.expires_at < time.monotonic():
            return None
        return item.proxy

    async def activate(self, session_id: str, proxy: ConsoleProxy) -> None:
        async with self._lock:
            self._active[session_id] = ConsoleSession(proxy=proxy, expires_at=time.monotonic() + self.active_ttl_seconds)

    async def get_active(self, session_id: str) -> ConsoleProxy | None:
        async with self._lock:
            item = self._active.get(session_id)
            if item is not None:
                if item.expires_at < time.monotonic():
                    self._active.pop(session_id, None)
                    return None
                item.expires_at = time.monotonic() + self.active_ttl_seconds
                return item.proxy

            item = self._items.get(session_id)
            if item is None or item.expires_at < time.monotonic():
                self._items.pop(session_id, None)
                return None
            return item.proxy

    async def discard(self, session_id: str) -> None:
        async with self._lock:
            self._items.pop(session_id, None)
            self._active.pop(session_id, None)


async def bridge_console(websocket: WebSocket, proxy: ConsoleProxy) -> None:
    ssl_context: ssl.SSLContext | None = None
    if proxy.websocket_url.startswith("wss://"):
        ssl_context = ssl.create_default_context()
        if not proxy.verify_tls:
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

    await websocket.accept()
    try:
        async with connect(
            proxy.websocket_url,
            additional_headers={"Cookie": f"PVEAuthCookie={proxy.auth_ticket}", "Origin": proxy.pve_url},
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
            ssl=ssl_context,
        ) as upstream:
            async def browser_to_pve() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        return
                    if message.get("bytes") is not None:
                        await upstream.send(message["bytes"])
                    elif message.get("text") is not None:
                        await upstream.send(message["text"])

            async def pve_to_browser() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            tasks = [asyncio.create_task(browser_to_pve()), asyncio.create_task(pve_to_browser())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
    except (WebSocketDisconnect, asyncio.CancelledError):
        raise
    except Exception:
        if websocket.client_state.name == "CONNECTED":
            await websocket.close(code=1011, reason="Não foi possível conectar ao console PVE")
