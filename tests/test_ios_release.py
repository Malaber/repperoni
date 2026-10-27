"""Exercise the upload command wiring with stubbed Apple tools, never signing/uploading."""

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ios/RepperoniIOS/Scripts/upload_testflight.sh"


@pytest.mark.skipif(not SCRIPT.exists(), reason="iOS sources excluded from backend image")
@pytest.mark.parametrize("api_key", [False, True])
def test_cli_archive_and_upload_arguments(tmp_path, api_key):
    log = tmp_path / "commands.log"
    for name in ("xcodegen", "xcodebuild"):
        executable = tmp_path / name
        executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$REPPERONI_RELEASE_TEST_LOG"\n')
        executable.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "TMPDIR": str(tmp_path),
        "REPPERONI_RELEASE_TEST_LOG": str(log),
    }
    for name in ("ASC_KEY_PATH", "ASC_KEY_ID", "ASC_ISSUER_ID"):
        environment.pop(name, None)
    if api_key:
        environment.update(ASC_KEY_PATH="/fake/key.p8", ASC_KEY_ID="test", ASC_ISSUER_ID="issuer")
    subprocess.run(["bash", str(SCRIPT), "1.2.3", "42"], env=environment, check=True)
    arguments = log.read_text().splitlines()
    assert "archive" in arguments
    assert "-exportArchive" in arguments
    assert "MARKETING_VERSION=1.2.3" in arguments
    assert "CURRENT_PROJECT_VERSION=42" in arguments
    assert "PRODUCT_BUNDLE_IDENTIFIER=de.malaber.repperoni" in arguments
    assert arguments.count("-allowProvisioningUpdates") == 2
    assert arguments.count("-authenticationKeyPath") == (2 if api_key else 0)
