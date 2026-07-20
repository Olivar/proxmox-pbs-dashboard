from __future__ import annotations

import json
from pathlib import Path


class IpCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._values = self._load()

    def _load(self) -> dict[int, str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        result: dict[int, str] = {}
        for key, value in payload.items():
            try:
                vmid = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(value, str) and value:
                result[vmid] = value
        return result

    def get(self, vmid: int) -> str | None:
        return self._values.get(vmid)

    def set(self, vmid: int, ip: str) -> None:
        if not ip or self._values.get(vmid) == ip:
            return
        self._values[vmid] = ip
        self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps({str(k): v for k, v in sorted(self._values.items())}, indent=2) + "\n",
                encoding="utf-8",
            )
            temp_path.replace(self.path)
        except OSError:
            return
