import os
import time
from pathlib import Path

from pytest import MonkeyPatch

from app.workers.healthcheck import main


def test_worker_health_requires_a_recent_successful_heartbeat(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    heartbeat = tmp_path / "worker.heartbeat"
    monkeypatch.setenv("UNIT_HOLD_EXPIRY_HEARTBEAT_PATH", str(heartbeat))
    monkeypatch.setenv("UNIT_HOLD_EXPIRY_INTERVAL_SECONDS", "5")

    assert main() == 1
    heartbeat.touch()
    assert main() == 0

    old = time.time() - 31
    os.utime(heartbeat, (old, old))
    assert main() == 1
