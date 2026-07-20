from app.proxmox import select_guest_ip
from app.utils import format_uptime, state_display


def test_format_uptime() -> None:
    assert format_uptime(0) == "—"
    assert format_uptime(3660) == "01h 01m"
    assert format_uptime(90061) == "1d 01h 01m"


def test_state_display() -> None:
    assert state_display("running") == ("running", "Ligado")
    assert state_display("stopped") == ("stopped", "Desligado")


def test_select_guest_ip_prefers_private_ipv4() -> None:
    payload = {
        "result": [
            {
                "name": "eth0",
                "ip-addresses": [
                    {"ip-address": "2001:db8::10", "ip-address-type": "ipv6"},
                    {"ip-address": "192.168.10.25", "ip-address-type": "ipv4"},
                ],
            },
            {
                "name": "docker0",
                "ip-addresses": [{"ip-address": "172.17.0.1", "ip-address-type": "ipv4"}],
            },
        ]
    }
    assert select_guest_ip(payload, ("lo", "docker")) == "192.168.10.25"
