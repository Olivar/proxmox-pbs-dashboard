from __future__ import annotations

import pytest

from app.console import ConsoleProxy, ConsoleSessionStore


def test_console_proxy_builds_internal_pve_websocket_url() -> None:
    proxy = ConsoleProxy(
        pve_url="https://pve01.test:8006",
        node="pve-a",
        vmid=109,
        port=5901,
        vnc_ticket="PVEVNC:ticket/with spaces",
        auth_ticket="auth-ticket",
        verify_tls=False,
    )

    assert proxy.websocket_url == (
        "wss://pve01.test:8006/api2/json/nodes/pve-a/qemu/109/vncwebsocket"
        "?port=5901&vncticket=PVEVNC%3Aticket%2Fwith+spaces"
    )


@pytest.mark.asyncio
async def test_console_session_is_single_use() -> None:
    store = ConsoleSessionStore(ttl_seconds=90)
    proxy = ConsoleProxy("https://pve.test:8006", "pve01", 100, 5900, "vnc", "auth", False)

    await store.put("session", proxy)

    assert await store.take("session") == proxy
    assert await store.take("session") is None
