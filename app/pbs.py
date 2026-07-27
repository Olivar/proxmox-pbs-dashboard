from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings
from app.models import BackupInfo
from app.utils import pick, utc_from_epoch


class PbsError(RuntimeError):
    pass


@dataclass(slots=True)
class TaskAttempt:
    vmid: int
    started_at: datetime
    status: str
    detail: str | None = None


class PbsClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.pbs_base_url,
            timeout=settings.request_timeout_seconds,
            verify=settings.pbs_verify_tls,
            headers={
                "Authorization": f"PBSAPIToken {settings.pbs_token_id}:{settings.pbs_token_secret}",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def get_backups(self) -> dict[int, BackupInfo]:
        snapshots: dict[int, BackupInfo] = {}
        errors: list[str] = []

        for datastore in self.settings.datastore_names:
            for backup_type in ("vm", "ct"):
                try:
                    rows = await self._get_json(
                        f"/api2/json/admin/datastore/{quote(datastore, safe='')}/snapshots",
                        params={"backup-type": backup_type},
                    )
                except PbsError as exc:
                    errors.append(f"{datastore}/{backup_type}: {exc}")
                    continue
                if not isinstance(rows, list):
                    errors.append(f"{datastore}/{backup_type}: resposta de snapshots inválida")
                    continue
                self._merge_snapshots(snapshots, datastore, rows)

        if errors and not snapshots:
            raise PbsError("; ".join(errors))

        try:
            tasks = await self._get_json(
                f"/api2/json/nodes/{quote(self.settings.pbs_node, safe='')}/tasks",
                params={"limit": self.settings.pbs_task_limit},
            )
            attempts = parse_backup_tasks(tasks, set(self.settings.datastore_names))
            merge_task_attempts(snapshots, attempts)
        except PbsError:
            pass

        return snapshots

    def _merge_snapshots(
        self,
        target: dict[int, BackupInfo],
        datastore: str,
        rows: list[Any],
    ) -> None:
        for row in rows:
            if not isinstance(row, dict):
                continue
            backup_type = str(pick(row, "backup-type", "backup_type", default="")).lower()
            if backup_type and backup_type not in {"vm", "ct"}:
                continue
            try:
                vmid = int(pick(row, "backup-id", "backup_id"))
            except (TypeError, ValueError):
                continue
            backup_time = utc_from_epoch(pick(row, "backup-time", "backup_time"))
            if backup_time is None:
                continue
            current = target.get(vmid)
            if current is None or current.last_backup is None or backup_time > current.last_backup:
                target[vmid] = BackupInfo(
                    datastore=datastore,
                    last_backup=backup_time,
                    status="success",
                    detail="Snapshot disponível no PBS",
                )

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            response = await self.client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PbsError(f"Falha ao consultar PBS: {exc}") from exc
        if not isinstance(payload, dict) or "data" not in payload:
            raise PbsError("Resposta inválida da API PBS")
        return payload["data"]


_VM_PATTERNS = (
    re.compile(r"(?:^|[^a-z0-9])(?:vm|ct)[/\s:_-]+(?P<vmid>\d+)(?:[^0-9]|$)", re.IGNORECASE),
    re.compile(r"(?:backup-id|backup_id|vmid)[=:/\s]+(?P<vmid>\d+)", re.IGNORECASE),
)


def parse_backup_tasks(data: Any, datastores: set[str] | None = None) -> dict[int, TaskAttempt]:
    if not isinstance(data, list):
        return {}

    latest: dict[int, TaskAttempt] = {}
    for row in data:
        if not isinstance(row, dict):
            continue
        worker_type = str(pick(row, "worker-type", "worker_type", "type", default="")).lower()
        if worker_type != "backup":
            continue

        worker_id = str(pick(row, "worker-id", "worker_id", default=""))
        upid = str(pick(row, "upid", default=""))
        identifier = " ".join(part for part in (worker_id, upid) if part)
        if datastores and not any(_contains_datastore(identifier, store) for store in datastores):
            continue

        text = identifier or " ".join(str(value) for value in row.values() if value is not None)
        vmid = extract_vmid(text)
        if vmid is None:
            continue

        started_at = utc_from_epoch(pick(row, "starttime", "start-time", "start_time"))
        if started_at is None:
            continue

        endtime = pick(row, "endtime", "end-time", "end_time")
        raw_status = str(pick(row, "status", "exitstatus", "exit-status", default="")).strip()
        if endtime in (None, 0, "0") and not raw_status:
            status = "running"
            detail = "Backup em execução"
        elif raw_status.upper() == "OK":
            status = "success"
            detail = "Tarefa PBS concluída com sucesso"
        elif raw_status:
            status = "failed"
            detail = raw_status
        else:
            status = "unknown"
            detail = "Tarefa PBS sem status conclusivo"

        attempt = TaskAttempt(vmid=vmid, started_at=started_at, status=status, detail=detail)
        current = latest.get(vmid)
        if current is None or attempt.started_at > current.started_at:
            latest[vmid] = attempt
    return latest


def _contains_datastore(text: str, datastore: str) -> bool:
    if not text or not datastore:
        return False
    pattern = re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(datastore)}(?![A-Za-z0-9_.-])", re.IGNORECASE)
    return pattern.search(text) is not None


def extract_vmid(text: str) -> int | None:
    for pattern in _VM_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return int(match.group("vmid"))
            except (TypeError, ValueError):
                return None
    return None


def merge_task_attempts(backups: dict[int, BackupInfo], attempts: dict[int, TaskAttempt]) -> None:
    for vmid, attempt in attempts.items():
        current = backups.get(vmid)
        if current is None:
            backups[vmid] = BackupInfo(
                last_backup=None,
                status=attempt.status if attempt.status in {"failed", "running"} else "unknown",
                detail=attempt.detail,
            )
            continue

        if current.last_backup is None or attempt.started_at > current.last_backup:
            current.status = attempt.status  # type: ignore[assignment]
            current.detail = attempt.detail
