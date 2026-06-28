import subprocess
from pathlib import Path

import pytest

from cnc_controller.update_status import UpdateManager, UpdateStatusStore


def test_pull_counter_only_increments_for_successful_pull(tmp_path: Path):
    store = UpdateStatusStore(tmp_path / "status.json")

    first = store.record("current", "abc123", "Already current.")
    second = store.record("updated", "def456", "Updated.", pulled=True)
    third = store.record("current", "def456", "Already current.")

    assert first.pull_count == 0
    assert second.pull_count == 1
    assert third.pull_count == 1
    assert third.last_pull_at == second.last_pull_at


def test_update_status_survives_invalid_file(tmp_path: Path):
    path = tmp_path / "status.json"
    path.write_text("not json")

    status = UpdateStatusStore(path).load()

    assert status.pull_count == 0
    assert status.last_pull_display == "Never"


def test_check_now_starts_user_sync_service(tmp_path: Path):
    store = UpdateStatusStore(tmp_path / "status.json")
    store.record("current", "abc123", "Already current.")
    commands = []

    def runner(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    status = UpdateManager(store, runner).check_now()

    assert commands == [
        ["systemctl", "--user", "start", "cnc-git-sync.service"]
    ]
    assert status.current_commit == "abc123"


def test_check_now_reports_service_failure(tmp_path: Path):
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "network unavailable")

    with pytest.raises(RuntimeError, match="network unavailable"):
        UpdateManager(UpdateStatusStore(tmp_path / "status.json"), runner).check_now()
