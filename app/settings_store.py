from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from app.config import PbsInstance, PveInstance, validate_pbs_instances, validate_pve_instances

ALLOWED_KEYS = (
    "DASHBOARD_TITLE",
    "DASHBOARD_USERNAME",
    "DASHBOARD_PASSWORD",
    "DASHBOARD_SESSION_SECRET",
    "DASHBOARD_DEFAULT_THEME",
    "REFRESH_SECONDS",
    "PBS_INSTANCES_JSON",
    "PBS_URL",
    "PBS_TOKEN_ID",
    "PBS_TOKEN_SECRET",
    "PBS_DATASTORES",
    "PBS_NODE",
    "PBS_VERIFY_TLS",
)
SECRET_KEYS = {"DASHBOARD_PASSWORD", "DASHBOARD_SESSION_SECRET", "PBS_TOKEN_SECRET"}
MASK = "********"
PVE_KEY = "PVE_INSTANCES_JSON"
PBS_KEY = "PBS_INSTANCES_JSON"


def read_env(path: Path) -> dict[str, str]:
    try:
        values = dotenv_values(path)
    except OSError:
        return {}
    return {str(key): str(value) for key, value in values.items() if value is not None}


def masked_settings(path: Path) -> dict[str, str]:
    values = read_env(path)
    return {key: (MASK if key in SECRET_KEYS and values.get(key) else values.get(key, "")) for key in ALLOWED_KEYS}


def masked_pve_settings(instances: list[PveInstance]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "name": item.name,
            "url": item.base_url,
            "token_id": item.token_id,
            "token_secret": MASK,
            "verify_tls": item.verify_tls,
        }
        for item in instances
    ]


def masked_pbs_settings(instances: list[PbsInstance]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "name": item.name,
            "url": item.base_url,
            "token_id": item.token_id,
            "token_secret": MASK,
            "datastores": item.datastores,
            "node": item.node,
            "verify_tls": item.verify_tls,
        }
        for item in instances
    ]


def write_env(
    path: Path,
    updates: dict[str, str],
    pve_updates: list[dict[str, Any]],
    current_instances: list[PveInstance],
    pbs_updates: list[dict[str, Any]] | None = None,
    current_pbs_instances: list[PbsInstance] | None = None,
) -> None:
    pbs_updates = pbs_updates or []
    current_pbs_instances = current_pbs_instances or []
    current = read_env(path)
    for key in ALLOWED_KEYS:
        if key not in updates:
            continue
        value = str(updates[key]).strip()
        if key in SECRET_KEYS and value in {"", MASK}:
            continue
        current[key] = value

    current_by_id = {item.id.casefold(): item for item in current_instances}
    normalized_payload: list[dict[str, Any]] = []
    for index, raw in enumerate(pve_updates, start=1):
        pve_id = str(raw.get("id", "")).strip()
        existing = current_by_id.get(pve_id.casefold())
        secret = str(raw.get("token_secret", "")).strip()
        if secret in {"", MASK}:
            if existing is None:
                raise ValueError(f"Informe o token secret do novo PVE #{index}")
            secret = existing.token_secret
        normalized_payload.append(
            {
                "id": pve_id,
                "name": str(raw.get("name", "")).strip(),
                "url": str(raw.get("url", "")).strip(),
                "token_id": str(raw.get("token_id", "")).strip(),
                "token_secret": secret,
                "verify_tls": bool(raw.get("verify_tls", True)),
            }
        )

    validated = validate_pve_instances(normalized_payload, PVE_KEY)
    current[PVE_KEY] = json.dumps([item.model_dump(mode="json") for item in validated], ensure_ascii=False, separators=(",", ":"))

    if pbs_updates:
        current_pbs_by_id = {item.id.casefold(): item for item in current_pbs_instances}
        normalized_pbs_payload: list[dict[str, Any]] = []
        for index, raw in enumerate(pbs_updates, start=1):
            pbs_id = str(raw.get("id", "")).strip()
            existing = current_pbs_by_id.get(pbs_id.casefold())
            secret = str(raw.get("token_secret", "")).strip()
            if secret in {"", MASK}:
                if existing is None:
                    raise ValueError(f"Informe o token secret do novo PBS #{index}")
                secret = existing.token_secret
            normalized_pbs_payload.append(
                {
                    "id": pbs_id,
                    "name": str(raw.get("name", "")).strip(),
                    "url": str(raw.get("url", "")).strip(),
                    "token_id": str(raw.get("token_id", "")).strip(),
                    "token_secret": secret,
                    "datastores": str(raw.get("datastores", "")).strip(),
                    "node": str(raw.get("node", "localhost")).strip() or "localhost",
                    "verify_tls": bool(raw.get("verify_tls", True)),
                }
            )

        validated_pbs = validate_pbs_instances(normalized_pbs_payload, PBS_KEY)
        current[PBS_KEY] = json.dumps([item.model_dump(mode="json") for item in validated_pbs], ensure_ascii=False, separators=(",", ":"))

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)

    output: list[str] = []
    seen: set[str] = set()
    deprecated = {"PVE_INSTANCES_FILE", "PVE_URL", "PVE_TOKEN_ID", "PVE_TOKEN_SECRET", "PVE_VERIFY_TLS"}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                output.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key in deprecated:
                continue
            if key in current:
                output.append(format_env_line(key, current[key]))
                seen.add(key)
            else:
                output.append(line)
    except FileNotFoundError:
        pass

    for key in (*ALLOWED_KEYS, PVE_KEY, PBS_KEY):
        if key in current and key not in seen:
            output.append(format_env_line(key, current[key]))

    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(temp, 0o660)
    temp.replace(path)


def format_env_line(key: str, value: str) -> str:
    if key == PVE_KEY or any(char.isspace() for char in value) or any(char in value for char in '#"\\'):
        return f"{key}={json.dumps(value, ensure_ascii=False)}"
    return f"{key}={value}"
