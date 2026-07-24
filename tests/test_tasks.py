import sys
from pathlib import Path

import pytest

from tasks import (
    _latest_stable_version,
    _resolved_revision,
    _uvicorn_command,
    _verify_version_url,
    _version_values,
    _write_public_audit_lock,
    docker_smoke,
)


ROOT = Path(__file__).resolve().parents[1]


def test_versioning_ignores_non_release_tags():
    tags = ["v0.1.0", "v0.1.2", "v0.2.0-rc.5", "other"]
    assert _latest_stable_version(tags) == "0.1.2"
    assert _version_values("main", 9, tags)["release_version"] == "0.1.3"


def test_branch_versions_avoid_existing_rc_tags():
    values = _version_values("feature", 5, ["v0.1.0", "v0.1.1-rc.5"])
    assert values == {
        "base_version": "0.1.1",
        "release_version": "0.1.1-rc.6",
        "git_tag": "v0.1.1-rc.6",
    }


def test_uvicorn_command_uses_invoking_python():
    command = _uvicorn_command(8123)
    assert command == [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8123",
    ]


def test_environment_bootstrap_is_hash_locked():
    setup = (ROOT / "scripts/setup_env.sh").read_text(encoding="utf-8")
    tasks = (ROOT / "tasks.py").read_text(encoding="utf-8")
    assert "pip install invoke" not in setup
    assert "--require-hashes -r requirements-bootstrap.lock" in setup
    assert "--require-hashes -r requirements-dev.lock" in tasks
    assert "--no-deps --no-build-isolation -e ." in tasks
    assert "--ignore-matching-lines='^[[:space:]]*#'" in tasks
    assert 'c.run("npm run check:js")' in tasks


def test_verify_includes_security_locks_and_optional_docker():
    tasks = (ROOT / "tasks.py").read_text(encoding="utf-8")
    verify_body = tasks.split("def verify(c):", 1)[1].split("\n\n", 1)[0]
    assert "check_locks.body(c)" in verify_body
    assert "security_check.body(c)" in verify_body
    assert 'shutil.which("docker")' in verify_body
    assert "docker_build_test.body(c)" in verify_body
    assert "docker_smoke.body(c)" in verify_body


def test_revision_validation_requires_full_lowercase_sha(monkeypatch):
    revision = "a" * 40
    assert _resolved_revision(revision) == revision
    monkeypatch.setattr("tasks._git_lines", lambda *_: [revision])
    assert _resolved_revision() == revision
    with pytest.raises(ValueError):
        _resolved_revision("abc123")


def test_version_verification_rejects_wrong_revision(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return b'{"status":"ok","revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'

    monkeypatch.setattr("tasks.urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match="Unexpected deployed version"):
        _verify_version_url("http://localhost/health/version", "a" * 40)


def test_docker_smoke_runs_valid_production_config_and_checks_revision(monkeypatch):
    class Context:
        def __init__(self):
            self.commands = []

        def run(self, command, **kwargs):
            self.commands.append((command, kwargs))

    context = Context()
    revision = "a" * 40
    verified = []
    monkeypatch.setattr("tasks._wait_for_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "tasks._verify_version_url",
        lambda url, expected: verified.append((url, expected)),
    )

    docker_smoke.body(context, port=8123, revision=revision)

    run_command, run_options = next(
        item for item in context.commands if item[0].startswith("docker run")
    )
    assert "-p 127.0.0.1:8123:8000" in run_command
    assert "-e APP_BASE_URL=https://repperoni.invalid" in run_command
    assert "-e ENVIRONMENT=production" in run_command
    assert "-e REGISTRATION_MODE=closed" in run_command
    assert "-e SECRET_KEY " in run_command
    assert "-e SECURE_COOKIES=true" in run_command
    assert "-e WEBAUTHN_RP_ID=repperoni.invalid" in run_command
    assert len(run_options["env"]["SECRET_KEY"]) == 64
    assert verified == [("http://localhost:8123/health/version", revision)]


def test_public_audit_lock_excludes_complete_direct_url_entries(tmp_path):
    source = tmp_path / "requirements.lock"
    target = tmp_path / "audit.lock"
    source.write_text(
        "public==1.2.3 \\\n"
        "    --hash=sha256:public\n"
        "private @ https://example.invalid/private-2.0.whl#sha256=private \\\n"
        "    --hash=sha256:private\n"
        "other==3.0 \\\n"
        "    --hash=sha256:other\n",
        encoding="utf-8",
    )

    assert _write_public_audit_lock(source, target) == ["private"]
    assert target.read_text(encoding="utf-8") == (
        "public==1.2.3 \\\n"
        "    --hash=sha256:public\n"
        "other==3.0 \\\n"
        "    --hash=sha256:other\n"
    )
