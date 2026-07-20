from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PveInstance(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    url: HttpUrl
    token_id: str = Field(min_length=1)
    token_secret: str = Field(min_length=1)
    verify_tls: bool = True

    @field_validator("id", "name", "token_id", "token_secret")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value

    @property
    def base_url(self) -> str:
        return str(self.url).rstrip("/")


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

    pve_instances_file: Path = Path("/etc/proxmox-pbs-dashboard/pve-instances.json")

    # Compatibilidade com a configuração anterior de um único PVE.
    pve_url: HttpUrl | None = None
    pve_token_id: str | None = None
    pve_token_secret: str | None = None
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

    @field_validator("pve_token_id", "pve_token_secret")
    @classmethod
    def strip_optional_secret(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("pbs_token_id", "pbs_token_secret", "pbs_datastores")
    @classmethod
    def non_empty_secret(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value

    @property
    def pbs_base_url(self) -> str:
        return str(self.pbs_url).rstrip("/")

    @property
    def datastore_names(self) -> list[str]:
        return [item.strip() for item in self.pbs_datastores.split(",") if item.strip()]

    @property
    def excluded_interfaces(self) -> tuple[str, ...]:
        return tuple(item.strip().lower() for item in self.excluded_interface_prefixes.split(",") if item.strip())

    def load_pve_instances(self) -> list[PveInstance]:
        if self.pve_instances_file.exists():
            return _read_pve_instances(self.pve_instances_file)

        if self.pve_url and self.pve_token_id and self.pve_token_secret:
            return [
                PveInstance(
                    id="pve",
                    name="PVE",
                    url=self.pve_url,
                    token_id=self.pve_token_id,
                    token_secret=self.pve_token_secret,
                    verify_tls=self.pve_verify_tls,
                )
            ]

        raise ValueError(
            f"Nenhuma instância PVE configurada. Crie {self.pve_instances_file} "
            "ou defina PVE_URL, PVE_TOKEN_ID e PVE_TOKEN_SECRET."
        )

    def load_ip_overrides(self) -> dict[int, str]:
        return _read_ip_map(self.ip_overrides_file)


def _read_pve_instances(path: Path) -> list[PveInstance]:
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Arquivo de instâncias PVE não encontrado: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Não foi possível ler o arquivo de instâncias PVE {path}: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise ValueError(f"O arquivo {path} deve conter uma lista JSON não vazia")

    instances: list[PveInstance] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Instância PVE #{index} inválida: esperado objeto JSON")
        try:
            instance = PveInstance.model_validate(item)
        except Exception as exc:
            raise ValueError(f"Instância PVE #{index} inválida: {exc}") from exc
        normalized_id = instance.id.casefold()
        if normalized_id in seen_ids:
            raise ValueError(f"ID de instância PVE duplicado: {instance.id}")
        seen_ids.add(normalized_id)
        instances.append(instance)
    return instances


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
