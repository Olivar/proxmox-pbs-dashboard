from datetime import UTC, datetime

from app.models import BackupInfo
from app.pbs import extract_vmid, merge_task_attempts, parse_backup_tasks


def test_extract_vmid() -> None:
    assert extract_vmid("backup:store:vm/120/2026-07-20") == 120
    assert extract_vmid("backup-id=305") == 305


def test_parse_failed_task() -> None:
    tasks = [
        {
            "worker-type": "backup",
            "worker-id": "store:vm/120/2026-07-20T02:00:00Z",
            "starttime": 1_752_980_400,
            "endtime": 1_752_980_500,
            "status": "TASK ERROR: connection reset",
        }
    ]
    result = parse_backup_tasks(tasks, {"store"})
    assert result[120].status == "failed"


def test_newer_task_overrides_snapshot_status() -> None:
    backups = {
        120: BackupInfo(
            datastore="store",
            last_backup=datetime(2026, 7, 19, 2, tzinfo=UTC),
            status="success",
        )
    }
    attempts = parse_backup_tasks([
        {
            "worker-type": "backup",
            "worker-id": "store:vm/120/2026-07-20T02:00:00Z",
            "starttime": int(datetime(2026, 7, 20, 2, tzinfo=UTC).timestamp()),
            "endtime": int(datetime(2026, 7, 20, 2, 5, tzinfo=UTC).timestamp()),
            "status": "TASK ERROR: failed",
        }
    ], {"store"})
    merge_task_attempts(backups, attempts)
    assert backups[120].status == "failed"
    assert backups[120].last_backup == datetime(2026, 7, 19, 2, tzinfo=UTC)
