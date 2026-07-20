from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    dashboard_title: str = "Proxmox / PBS"
    listen_host: str = "0.0.0.0"
    listen_port: int = Field(default=8080, ge=1, le=65535)
    refresh_seconds: int = Field(default=60, ge=15, le=3600)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    max_parallel_guest_agent_requests: int = Field(default=8, ge=1, le=64)

    pve_url: HttpUrl
    pve_token_id: str
    pve_token_secret: str
    pve_verify_tls: bool = True

    pbs_url: HttpUrl
    pbs_token_id: str
    pbs_token_secret: str
    pbs_datastores: str
    pbs_node: str = "localhost"
    pbs_verify_tls: bool = True
    pbs_task_limit: int = Field(default=500, ge=50, le=5000)

    ip_overrides_file: Path = Path("/etc/proxmox-pbs-dashboard/ip-overrides.json")
    ip_cache_file: Path = Path("/var/lib/proxmox-pbs-dashboard/ip-cache.json")
    excluded_interface_prefixes: str = "lo,docker,veth,br-,virbr,podman,cni,tun,tap,wg,tailscale,zt"

    @field_validator("pve_token_id", "pve_token_secret", "pbs_token_id", "pbs_token_secret", "pbs_datastores")
    @classmethod
    def non_empty_secret(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value

    @property
    def pve_base_url(self) -> str:
        return str(self.pve_url).rstrip("/")

    @property
    def pbs_base_url(self) -> str:
        return str(self.pbs_url).rstrip("/")

    @property
    def datastore_names(self) -> list[str]:
        return [item.strip() for item in self.pbs_datastores.split(",") if item.strip()]

    @property
    def excluded_interfaces(self) -> tuple[str, ...]:
        return tuple(item.strip().lower() for item in self.excluded_interface_prefixes.split(",") if item.strip())

    def load_ip_overrides(self) -> dict[int, str]:
        return _read_ip_map(self.ip_overrides_file)


def _read_ip_map(path: Path) -> dict[int, str]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    result: dict[int, str] = {}
    for key, value in payload.items():
        try:
            vmid = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, str) and value.strip():
            result[vmid] = value.strip()
    return result


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
