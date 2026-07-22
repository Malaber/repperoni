from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_ci_gates_images_on_all_checks():
    workflow = read(".github/workflows/ci.yml")
    assert "python_pytest" in workflow
    assert "javascript_test" in workflow
    assert "browser_e2e" in workflow
    assert "linux/amd64" in workflow and "linux/arm64" in workflow
    assert "sha-${{ github.sha }}" in workflow


def test_review_deploy_waits_for_health_and_e2e():
    workflow = read(".github/workflows/pr-review.yml")
    assert "X-Hub-Signature-256" in workflow
    assert "retry 36" in workflow
    assert "run-browser-e2e" in workflow
    assert "bootstrap-ci" in workflow
    assert "pr-$PR_NUMBER.pr.repperoni.malaber.de" in workflow


def test_release_promotes_the_tested_sha():
    workflow = read(".github/workflows/release.yml")
    assert "workflow_run" in workflow
    assert "sha-${{ github.event.workflow_run.head_sha }}" in workflow
    assert "imagetools create" in workflow
    assert 'X-GitHub-Event": "push' in workflow


def test_webhooker_configs_isolate_review_data():
    review = read("deploy/webhooker/config/repperoni-review.yaml")
    production = read("deploy/webhooker/config/repperoni-production.yaml")
    compose = read("deploy/webhooker/compose.review.yml")
    assert "cleanup_closed_prs: true" in review
    assert "pr-{pr}/repperoni.db" in review
    assert "production_hostname: repperoni.malaber.de" in production
    assert "system_traefik_external" in compose


def test_docker_runs_as_non_root_with_healthcheck():
    dockerfile = read("Dockerfile")
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "--proxy-headers" in read("docker/start.sh")
