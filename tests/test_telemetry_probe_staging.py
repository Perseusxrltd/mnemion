"""The relocated diagnostic controller must load its phase helper."""

import os
from pathlib import Path
import subprocess

from deploy.probe_telemetry_renderer import stage_renderer_controller

ROOT = Path(__file__).resolve().parents[1]


def test_relocated_controller_reaches_the_disposable_profile_guard(tmp_path):
    application = tmp_path / "electron"
    application.mkdir()
    stage_renderer_controller(ROOT, application)
    environment = os.environ.copy()
    environment.pop("MNEMION_STUDIO_USER_DATA", None)
    completed = subprocess.run(
        ["node", str(application / "probe-telemetry-renderer.mjs")],
        cwd=application,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = f"{completed.stdout}{completed.stderr}"
    assert "ERR_MODULE_NOT_FOUND" not in output
    assert "Disposable renderer profile required" in output
    assert completed.returncode == 1
