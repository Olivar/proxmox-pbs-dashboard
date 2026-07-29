from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

ALLOWED_KEYS = (
    "DASHBOARD_TITLE",
    "DASHBOARD_USERNAME",
    "DASHBOARD_PASSWORD",
    "DASHBOARD_SESSION_SECRET",
    "DASHBOARD_DEFAULT_THEME",
    "REFRESH_SECONDS",
    "PBS_URL",
    "PBS_TOKEN_ID",
    "PBS_TOKEN_SECRET",
    "PBS_DATASTORES",
    "PBS_NODE",
    "PBS_VERIFY_TLS",
)
SECRET_KEYS = {"DASHBOARD_PASSWORD", "DASHBOARD_SESSION_SECRET", "PBS_TOKEN_SECRET"}


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return result
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def masked_settings(path: Path) -> dict[str, str]:
    values = read_env(path)
    return {key: ("********" if key in SECRET_KEYS and values.get(key) else values.get(key, "")) for key in ALLOWED_KEYS}


def write_env(path: Path, updates: dict[str, str]) -> None:
    current = read_env(path)
    for key in ALLOWED_KEYS:
        if key not in updates:
            continue
        value = updates[key].strip()
        if key in SECRET_KEYS and value in {"", "********"}:
            continue
        current[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(path, backup)

    ordered: list[str] = []
    seen: set[str] = set()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                ordered.append(line)
                continue
            key = line.split("=", 1)[0].strip()
            if key in current:
                ordered.append(f"{key}={current[key]}")
                seen.add(key)
            else:
                ordered.append(line)
    except FileNotFoundError:
        pass
    for key in ALLOWED_KEYS:
        if key in current and key not in seen:
            ordered.append(f"{key}={current[key]}")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text("\n".join(ordered).rstrip() + "\n", encoding="utf-8")
    os.chmod(temp, 0o660)
    temp.replace(path)
