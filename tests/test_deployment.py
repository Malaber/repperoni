import re
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
    assert "REPPERONI_REVISION=${{ env.SOURCE_SHA }}" in workflow
    assert "pull_request:" in workflow
    assert "packages: write" not in workflow
    assert workflow.count("persist-credentials: false") == workflow.count("actions/checkout@")


def test_privileged_publisher_never_checks_out_untrusted_code():
    workflow = read(".github/workflows/publish.yml")
    assert "workflow_run:" in workflow
    assert "workflows: [CI]" in workflow
    assert "packages: write" in workflow
    assert "actions/checkout@" not in workflow
    assert "github.event.workflow_run.id" in workflow
    assert "head_repository.full_name == github.repository" in workflow
    assert "org.opencontainers.image.revision" in workflow
    assert "attest-build-provenance@" in workflow
    assert "uses: ./.github/workflows/pr-review.yml" in workflow
    assert "uses: ./.github/workflows/release.yml" in workflow
    assert "WEBHOOKER_" not in workflow


def test_review_deploy_waits_for_health_and_e2e():
    workflow = read(".github/workflows/pr-review.yml")
    deploy_job, untrusted_job = workflow.split("  deployed_e2e:", 1)
    untrusted_job = untrusted_job.split("  comment:", 1)[0]
    assert "workflow_call:" in workflow
    assert "environment: review" in deploy_job
    assert "actions/checkout@" not in deploy_job
    assert "WEBHOOKER_REVIEW_WEBHOOK_SECRET" in deploy_job
    assert "WEBHOOKER_" not in untrusted_job
    assert "docker/login-action@" not in untrusted_job
    assert "persist-credentials: false" in untrusted_job
    assert "--signer-workflow" in deploy_job
    assert "X-Hub-Signature-256" in workflow
    assert "retry 36" in workflow
    assert "/health/version" in workflow
    assert "run-browser-e2e" in workflow
    assert "bootstrap-ci" in workflow
    assert "pr-$PR_NUMBER.repperoni-review.malaber.de" in workflow


def test_release_promotes_the_tested_sha():
    workflow = read(".github/workflows/release.yml")
    assert "workflow_call:" in workflow
    assert "environment: production" in workflow
    assert "ref: ${{ inputs.revision }}" in workflow
    assert '[[ "$(git rev-parse origin/main)" == "$REVISION" ]]' in workflow
    assert "--signer-workflow" in workflow
    assert '"$IMAGE@$DIGEST"' in workflow
    assert "imagetools create" in workflow
    assert "/health/version" in workflow
    assert 'X-GitHub-Event": "push' in workflow


def test_third_party_actions_are_immutable():
    uses_pattern = re.compile(r"^\s*(?:-\s+)?uses:\s+([^#\s]+)", re.MULTILINE)
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for reference in uses_pattern.findall(path.read_text(encoding="utf-8")):
            if reference.startswith("./"):
                assert reference.startswith("./.github/workflows/")
                continue
            assert re.fullmatch(
                r"[^@\s]+@[0-9a-f]{40}", reference
            ), f"{path.name} has mutable action reference {reference}"
