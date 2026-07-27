from __future__ import annotations

import json
import threading
from pathlib import Path


class NoteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._values = self._load()

    @staticmethod
    def key(pve_id: str, vmid: int) -> str:
        return f"{pve_id}:{vmid}"

    def _load(self) -> dict[str, str]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(key): value.strip()
            for key, value in payload.items()
            if isinstance(value, str) and value.strip()
        }

    def get(self, pve_id: str, vmid: int) -> str:
        with self._lock:
            return self._values.get(self.key(pve_id, vmid), "")

    def set(self, pve_id: str, vmid: int, note: str) -> str:
        cleaned = note.strip()
        key = self.key(pve_id, vmid)
        with self._lock:
            if cleaned:
                self._values[key] = cleaned
            else:
                self._values.pop(key, None)
            self._save()
        return cleaned

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(dict(sorted(self._values.items())), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)
