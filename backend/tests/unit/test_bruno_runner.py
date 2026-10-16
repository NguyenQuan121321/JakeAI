"""CLI orchestration must report stalled external commands as failures."""

import importlib.util
import subprocess
import sys
import time
from pathlib import Path


def test_stalled_bruno_command_fails_within_deadline(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[3] / "scripts/run_bruno_tests.py"
    spec = importlib.util.spec_from_file_location("bruno_deadline_runner", source)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, runner)
    spec.loader.exec_module(runner)
    real_popen = subprocess.Popen

    def stalled_cli(_command, **options):
        # An actual child process exercises communicate/termination, without npm
        # downloads, application mocks or any provider traffic.
        if _command[0] == "synthetic-cli":
            return real_popen(
                [sys.executable, "-c", "import time; time.sleep(30)"], **options
            )
        return real_popen(_command, **options)

    monkeypatch.setattr(runner.subprocess, "Popen", stalled_cli)
    started = time.monotonic()
    code, items = runner.run_bruno_cli_target(
        "synthetic-cli",
        tmp_path,
        "stalled-request.bru",
        "Local",
        tmp_path / "report.json",
        timeout_seconds=0.15,
    )
    assert time.monotonic() - started < 10
    assert code != 0
    assert len(items) == 1
    assert items[0].status == "failed"
    assert items[0].error_message == "BRUNO_COMMAND_TIMEOUT"
