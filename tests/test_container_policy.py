from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_webhooker_configs_isolate_review_data():
    review = read("deploy/webhooker/config/repperoni-review.yaml")
    production = read("deploy/webhooker/config/repperoni-production.yaml")
    review_compose = read("deploy/webhooker/compose.review.yml")
    production_compose = read("deploy/webhooker/compose.production.yml")
    assert "cleanup_closed_prs: true" in review
    assert "pr-{pr}/repperoni.db" in review
    assert "hostname_template: pr-{pr}.repperoni-review.malaber.de" in review
    assert "pr.repperoni.malaber.de" not in review
    assert "tag_template: review-sha-{sha}" in review
    assert "production_hostname: repperoni.malaber.de" in production
    assert "REGISTRATION_MODE=closed" in read("deploy/webhooker/env/production.common.env")
    assert "system_traefik_reviews_external" in review_compose
    assert "system_traefik_external" not in review_compose.replace(
        "system_traefik_reviews_external", ""
    )
    assert "repperoni_traefik_external" in production_compose
    assert "      - default" not in review_compose


def test_docker_runs_as_fixed_non_root_without_trusting_forwarded_headers():
    dockerfile = read("Dockerfile")
    start = read("docker/start.sh")
    assert "useradd --uid 10001 --gid 10001" in dockerfile
    assert dockerfile.count("USER 10001:10001") >= 2
    assert "HEALTHCHECK" in dockerfile
    assert "REPPERONI_REVISION" in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
    assert "APP_REVISION=${REPPERONI_REVISION}" in dockerfile
    assert "python:3.14-slim@sha256:" in dockerfile
    assert "AUTO_MIGRATE=false" in dockerfile
    assert "pip install --no-cache-dir --require-hashes -r requirements.lock" in dockerfile
    assert "pip install --no-cache-dir --no-deps --no-build-isolation ." in dockerfile
    assert "COPY .dockerignore ./" in dockerfile
    assert "COPY .github ./.github" in dockerfile
    assert "deploy/webhooker/secrets/*.env" in read(".dockerignore")
    assert "--no-server-header" in start
    assert "--no-proxy-headers" in start
    assert "--forwarded-allow-ips" not in start


def test_compose_confines_application_containers():
    for path in (
        "deploy/webhooker/compose.review.yml",
        "deploy/webhooker/compose.production.yml",
    ):
        compose = read(path)
        assert "privileged: true" not in compose
        assert "docker.sock" not in compose
        assert "network_mode: host" not in compose
        assert 'user: "10001:10001"' in compose
        assert "pull_policy: always" in compose
        assert "read_only: true" in compose
        assert "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777" in compose
        assert "cap_drop:\n      - ALL" in compose
        assert "no-new-privileges:true" in compose
        assert "pids_limit: 128" in compose
        assert "mem_limit: 512m" in compose
        assert "cpus: 1.0" in compose
        assert 'max-size: "10m"' in compose
        assert 'max-file: "3"' in compose
        assert ".middlewares=${TRAEFIK_ROUTER}-body@docker,${TRAEFIK_ROUTER}-rate@docker" in compose
        assert "buffering.maxRequestBodyBytes=65536" in compose
        assert "ratelimit.average=20" in compose
        assert "ratelimit.burst=40" in compose
