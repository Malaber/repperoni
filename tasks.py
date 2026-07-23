import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from invoke import task


ROOT = Path(__file__).resolve().parent
TMP = ROOT / ".tmp"
PID_FILE = TMP / "repperoni.pid"
LOG_FILE = TMP / "repperoni.log"
STABLE_TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
MACOS_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _bin(name: str) -> str:
    local = ROOT / ".venv" / "bin" / name
    return shlex.quote(str(local if local.exists() else name))


def _clean_install_env() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        if environment.get(name) and not Path(environment[name]).exists():
            environment.pop(name)
    return environment


def _playwright_channel() -> str | None:
    configured = os.environ.get("PLAYWRIGHT_CHANNEL")
    if configured:
        return configured
    if sys.platform == "darwin" and MACOS_CHROME.exists():
        return "chrome"
    return None


def _git_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.splitlines()


def _latest_stable_version(tags: list[str]) -> str:
    versions = [
        tuple(map(int, match.groups()))
        for tag in tags
        if (match := STABLE_TAG_PATTERN.fullmatch(tag))
    ]
    if not versions:
        return "0.1.0"
    major, minor, patch = max(versions)
    return f"{major}.{minor}.{patch}"


def _next_stable_version(version: str, tags: list[str]) -> str:
    major, minor, patch = map(int, version.split("."))
    existing = set(tags)
    while True:
        patch += 1
        candidate = f"{major}.{minor}.{patch}"
        if f"v{candidate}" not in existing:
            return candidate


def _version_values(ref_name: str, run_number: int, tags: list[str]) -> dict[str, str]:
    base = _next_stable_version(_latest_stable_version(tags), tags)
    if ref_name == "main":
        release = base
    else:
        rc = run_number
        while f"v{base}-rc.{rc}" in tags:
            rc += 1
        release = f"{base}-rc.{rc}"
    return {"base_version": base, "release_version": release, "git_tag": f"v{release}"}


def _write_github_output(values: dict[str, str]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        for key, value in values.items():
            print(f"{key}={value}")
        return
    with Path(output_path).open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _stop_process() -> None:
    pid = _read_pid()
    if pid and _process_running(pid):
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            if not _process_running(pid):
                break
            time.sleep(0.1)
        else:
            os.kill(pid, signal.SIGKILL)
    PID_FILE.unlink(missing_ok=True)


def _uvicorn_command(port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def _wait_for_url(url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


@task
def setup_venv(c):
    """Create the Python 3.14 virtual environment."""
    if not (ROOT / ".venv" / "bin" / "python").exists():
        c.run("python3.14 -m venv .venv")


@task
def install_python(c):
    environment = _clean_install_env()
    c.run(
        f"{_bin('pip')} install --require-hashes -r requirements-dev.lock",
        env=environment,
    )
    c.run(
        f"{_bin('pip')} install --no-deps --no-build-isolation -e .",
        env=environment,
    )


@task
def install_js(c):
    command = "npm ci" if (ROOT / "package-lock.json").exists() else "npm install"
    c.run(command)


@task(install_python, install_js)
def install_deps(_):
    """Install all development dependencies."""


@task
def bootstrap_ci(c):
    python = shlex.quote(sys.executable)
    environment = _clean_install_env()
    c.run(
        f"{python} -m pip install --require-hashes -r requirements-dev.lock",
        env=environment,
    )
    c.run(
        f"{python} -m pip install --no-deps --no-build-isolation -e .",
        env=environment,
    )


@task
def lock_deps(c):
    """Regenerate hash-locked bootstrap, production, and development dependencies."""
    environment = {
        **_clean_install_env(),
        "CUSTOM_COMPILE_COMMAND": ".venv/bin/inv lock-deps",
    }
    common = "--quiet --generate-hashes --allow-unsafe --strip-extras --newline=lf"
    c.run(
        f"{_bin('pip-compile')} {common} --output-file=requirements-bootstrap.lock "
        "requirements-bootstrap.in",
        env=environment,
    )
    c.run(
        f"{_bin('pip-compile')} {common} --build-deps-for=wheel "
        "--output-file=requirements.lock pyproject.toml",
        env=environment,
    )
    c.run(
        f"{_bin('pip-compile')} {common} --build-deps-for=wheel --extra=dev "
        "--output-file=requirements-dev.lock pyproject.toml",
        env=environment,
    )


@task
def format(c):
    c.run(f"{_bin('black')} app tests tasks.py")


@task
def black_check(c):
    c.run(f"{_bin('black')} --check app tests tasks.py")


@task
def flake8_check(c):
    c.run(f"{_bin('flake8')} app tests tasks.py")


@task
def test_python(c):
    c.run(f"{_bin('pytest')}")


@task
def check_python(c):
    black_check.body(c)
    flake8_check.body(c)
    test_python.body(c)


@task
def check_js(c):
    c.run("npm run test:js")


@task
def audit_python(c):
    c.run(
        f"{_bin('pip-audit')} --requirement requirements.lock "
        "--disable-pip --require-hashes --strict --progress-spinner=off"
        " --cache-dir .tmp/pip-audit-cache"
    )


@task
def bandit_check(c):
    c.run(f"{_bin('bandit')} --quiet --recursive app")


@task
def security_check(c):
    """Audit locked Python/Node dependencies and scan Python security patterns."""
    audit_python.body(c)
    bandit_check.body(c)
    c.run("npm audit --audit-level=high")


@task
def install_browser(c):
    if channel := _playwright_channel():
        print(f"Using installed Playwright browser channel: {channel}")
        return
    c.run("npx playwright install chromium")


@task
def migrate(c):
    c.run(f"{_bin('alembic')} upgrade head")


@task
def start(c, host="127.0.0.1", port=8000, reload=False):
    reload_flag = " --reload" if reload else ""
    c.run(f"{_bin('uvicorn')} app.main:app --host {host} --port {port}{reload_flag}")


@task
def start_app(c, port=8000, e2e=False):
    """Start a background app used by browser and smoke tests."""
    _stop_process()
    TMP.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.setdefault("APP_BASE_URL", f"http://localhost:{port}")
    environment.setdefault("WEBAUTHN_RP_ID", "localhost")
    environment.setdefault("SECRET_KEY", "repperoni-local-e2e-secret")
    if e2e:
        database = TMP / "e2e.db"
        for suffix in ("", "-wal", "-shm"):
            Path(f"{database}{suffix}").unlink(missing_ok=True)
        environment["DATABASE_URL"] = f"sqlite+aiosqlite:///{database}"
        environment["REGISTRATION_MODE"] = "open"
    log = LOG_FILE.open("w", encoding="utf-8")
    process = subprocess.Popen(
        _uvicorn_command(port),
        cwd=ROOT,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.close()
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(f"Repperoni started as PID {process.pid}; log: {LOG_FILE}")


@task
def wait_for_app(_, port=8000, timeout=30):
    _wait_for_url(f"http://localhost:{port}/health", float(timeout))


@task
def stop_app(_):
    _stop_process()


@task
def run_browser_e2e(c, base_url="http://localhost:8000", device="all"):
    environment = {"REPPERONI_PYTHON": sys.executable}
    if channel := _playwright_channel():
        environment["PLAYWRIGHT_CHANNEL"] = channel
    c.run(
        "node scripts/run_ui_e2e.mjs "
        f"--base-url={shlex.quote(base_url)} --device={shlex.quote(device)}",
        env=environment,
    )


@task
def browser_e2e(c, port=8000, device="all"):
    start_app.body(c, port=port, e2e=True)
    try:
        wait_for_app.body(c, port=port, timeout=30)
        run_browser_e2e.body(c, base_url=f"http://localhost:{port}", device=device)
    finally:
        stop_app.body(c)


@task
def browser_e2e_mobile(c, port=8000):
    browser_e2e.body(c, port=port, device="mobile")


@task
def browser_e2e_desktop(c, port=8000):
    browser_e2e.body(c, port=port, device="desktop")


@task
def check_browser_e2e(c):
    browser_e2e.body(c, device="all")


@task
def verify(c):
    """Run the same Python, JavaScript, and browser checks as CI."""
    check_python.body(c)
    install_js.body(c)
    check_js.body(c)
    install_browser.body(c)
    check_browser_e2e.body(c)


@task
def verify_http(_, base_url="http://localhost:8000"):
    _wait_for_url(f"{base_url.rstrip('/')}/health", 30)
    print(f"Healthy: {base_url}")


@task
def docker_build(c):
    c.run("docker build --target production --build-arg REPPERONI_VERSION=dev -t repperoni:dev .")


@task
def docker_build_test(c):
    c.run("docker build --target test -t repperoni:test .")


@task
def docker_smoke(c, port=8010):
    docker_build.body(c)
    name = "repperoni-smoke"
    c.run(f"docker run -d --rm --name {name} -p {port}:8000 repperoni:dev")
    try:
        _wait_for_url(f"http://localhost:{port}/health", 45)
    finally:
        c.run(f"docker stop {name}", warn=True)


@task(help={"ref_name": "Git ref name", "run_number": "GitHub Actions run number"})
def compute_version(_, ref_name="", run_number=""):
    resolved_ref = ref_name or os.environ.get("REF_NAME") or os.environ.get("GITHUB_REF_NAME")
    resolved_run = run_number or os.environ.get("RUN_NUMBER") or os.environ.get("GITHUB_RUN_NUMBER")
    if not resolved_ref or not resolved_run:
        raise ValueError("compute-version requires ref_name and run_number")
    values = _version_values(resolved_ref, int(resolved_run), _git_lines("tag", "--list", "v*"))
    _write_github_output(values)
