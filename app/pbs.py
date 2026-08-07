from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from app.config import PbsInstance, Settings
from app.models import BackupInfo, PbsDatastoreSummary, PbsSummary, PbsTaskSummary
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
    def __init__(self, settings: Settings, instance: PbsInstance | None = None) -> None:
        self.settings = settings
        self.instance = instance or settings.load_pbs_instances()[0]
        self.client = httpx.AsyncClient(
            base_url=self.instance.base_url,
            timeout=settings.request_timeout_seconds,
            verify=self.instance.verify_tls,
            headers={
                "Authorization": f"PBSAPIToken {self.instance.token_id}:{self.instance.token_secret}",
                "Accept": "application/json",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def get_backups(self) -> dict[int, BackupInfo]:
        snapshots: dict[int, BackupInfo] = {}
        errors: list[str] = []

        for datastore in self.instance.datastore_names:
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
                f"/api2/json/nodes/{quote(self.instance.node, safe='')}/tasks",
                params={"limit": self.settings.pbs_task_limit},
            )
            attempts = parse_backup_tasks(tasks, set(self.instance.datastore_names))
            merge_task_attempts(snapshots, attempts)
        except PbsError:
            pass

        return snapshots

    async def get_summary(self) -> PbsSummary:
        node_path = f"/api2/json/nodes/{quote(self.instance.node, safe='')}"
        status_data, task_data, datastore_results = await asyncio.gather(
            self._get_optional_json(f"{node_path}/status"),
            self._get_optional_json(f"{node_path}/tasks", {"limit": self.settings.pbs_task_limit, "source": "all"}),
            asyncio.gather(*(self._get_datastore_status(name) for name in self.instance.datastore_names)),
        )
        status = status_data if isinstance(status_data, dict) else {}
        memory = status.get("memory") if isinstance(status.get("memory"), dict) else {}
        root = status.get("root") if isinstance(status.get("root"), dict) else {}
        ram_used = non_negative_int(pick(status, "memory-used", "memory_used", "mem", default=pick(memory, "used", default=0)))
        ram_total = non_negative_int(pick(status, "memory-total", "memory_total", "maxmem", default=pick(memory, "total", default=0)))
        datastores = [item for item in datastore_results if item is not None]
        disk_used = sum(item.used_bytes for item in datastores)
        disk_total = sum(item.total_bytes for item in datastores)
        if not disk_total:
            disk_used = non_negative_int(pick(root, "used", default=pick(status, "root-used", "root_used", default=0)))
            disk_total = non_negative_int(pick(root, "total", default=pick(status, "root-total", "root_total", default=0)))
        tasks = parse_pbs_tasks(task_data)
        tasks.sort(key=lambda task: task.start_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        cpu_info = status.get("cpuinfo") if isinstance(status.get("cpuinfo"), dict) else {}
        cpu_total = non_negative_int(pick(status, "cpus", "maxcpu", default=pick(cpu_info, "cpus", "cores", default=0)))
        return PbsSummary(
            pbs_id=self.instance.id,
            pbs_name=self.instance.name,
            pbs_url=self.instance.base_url,
            updated_at=datetime.now(timezone.utc),
            node=self.instance.node,
            status="online" if status else "unknown",
            cpu_percent=percent(pick(status, "cpu", default=0), 100),
            cpu_total_cores=cpu_total,
            ram_percent=ratio_percent(ram_used, ram_total),
            ram_used_bytes=ram_used,
            ram_total_bytes=ram_total,
            disk_percent=ratio_percent(disk_used, disk_total),
            disk_used_bytes=disk_used,
            disk_total_bytes=disk_total,
            datastores=datastores,
            tasks=tasks[:50],
        )

    async def _get_datastore_status(self, datastore: str) -> PbsDatastoreSummary | None:
        data = await self._get_optional_json(f"/api2/json/admin/datastore/{quote(datastore, safe='')}/status")
        if not isinstance(data, dict):
            return None
        total = non_negative_int(pick(data, "total", "total-bytes", "total_bytes", default=0))
        used = non_negative_int(pick(data, "used", "used-bytes", "used_bytes", default=0))
        avail = non_negative_int(pick(data, "avail", "available", "avail-bytes", "avail_bytes", default=0))
        if not total and used + avail:
            total = used + avail
        return PbsDatastoreSummary(
            name=datastore,
            status="online",
            used_bytes=used,
            total_bytes=total,
            avail_bytes=avail,
            percent=ratio_percent(used, total),
        )

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

    async def _get_optional_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            return await self._get_json(path, params)
        except PbsError:
            return None


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


def parse_pbs_tasks(data: Any) -> list[PbsTaskSummary]:
    if not isinstance(data, list):
        return []
    tasks: list[PbsTaskSummary] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        task_type = str(pick(row, "worker-type", "worker_type", "type", default="unknown"))
        task_id = str(pick(row, "worker-id", "worker_id", "id", default="")) or None
        raw_status = str(pick(row, "status", "exitstatus", "exit-status", default="")).strip()
        end_at = utc_from_epoch(pick(row, "endtime", "end-time", "end_time"))
        if not raw_status and end_at is None:
            status = "running"
        elif raw_status.upper() == "OK":
            status = "success"
        elif raw_status:
            status = raw_status
        else:
            status = "unknown"
        tasks.append(PbsTaskSummary(
            task_type=task_type,
            task_id=task_id,
            description=describe_pbs_task(task_type),
            status=status,
            start_at=utc_from_epoch(pick(row, "starttime", "start-time", "start_time")),
            end_at=end_at,
            upid=str(row["upid"]) if row.get("upid") is not None else None,
        ))
    return tasks


def describe_pbs_task(task_type: str) -> str:
    descriptions = {
        "backup": "Backup Job",
        "gc": "Garbage collection",
        "prune": "Prune job",
        "verify": "Verification job",
        "sync": "Sync job",
        "aptupdate": "Update package database",
        "acme": "ACME certificate renewal",
        "package-updates": "Package updates",
    }
    return descriptions.get(task_type.casefold(), task_type or "Unknown task")


def non_negative_int(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def percent(value: Any, scale: int = 1) -> int:
    try:
        return max(0, min(100, round(float(value or 0) * scale)))
    except (TypeError, ValueError):
        return 0


def ratio_percent(value: Any, maximum: Any) -> int:
    try:
        total = float(maximum or 0)
        return 0 if total <= 0 else max(0, min(100, round(float(value or 0) / total * 100)))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0
