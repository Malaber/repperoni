# Webhooker deployment

Repperoni follows the same tested-image contract as Planini and Tracy:

1. Unprivileged CI runs Python, JavaScript, desktop browser, mobile browser, dependency, and
   container tests.
2. CI scans each platform image, then uploads platform archives and SBOMs without registry
   credentials.
3. A default-branch `workflow_run` publisher validates the embedded revision and publishes it as
   `review-sha-<full-sha>` or `candidate-sha-<full-sha>`.
   It is the only job with registry write access and emits signed provenance.
4. An internal pull request receives a signed synthetic `pull_request` wake event that points
   Webhooker at that immutable `review-sha-<full-sha>` image.
5. Webhooker deploys it to `https://pr-<pr>.repperoni-review.malaber.de` with isolated SQLite.
   The workflow waits for health and runs mobile E2E before posting the URL.
6. Successful protected-main CI verifies the candidate digest and publisher identity inside the
   protected production environment, then creates the deployable `sha-<full-sha>`, semantic
   version, and `latest` tags before sending the signed production wake. Webhooker's main poller
   cannot deploy a candidate before this gate. Releases never rebuild or execute application code
   and fail if the deployed revision differs.

## Repository configuration

Create GitHub environments named `review` and `production`. Restrict both to the protected
`main` branch; reusable deploy workflows run from that trusted ref. Put
`WEBHOOKER_REVIEW_WAKE_URL` plus `WEBHOOKER_REVIEW_WEBHOOK_SECRET` only in `review`, and put
`WEBHOOKER_PRODUCTION_WAKE_URL` plus `WEBHOOKER_PRODUCTION_WEBHOOK_SECRET` only in `production`.
Do not store wake credentials as repository-wide secrets. Fork pull requests intentionally do
not publish or deploy.

Protect `main`: require the CI jobs, require pull requests, dismiss stale approvals, block force
pushes/deletion, and prevent bypass. The release job independently requires the revision to
remain the exact current `main` head.

Enable Dependabot security updates and the dependency graph. Keep the generated lock files and
the Docker base-image digest under review; CI rejects drift and known high/critical
vulnerabilities.

## Host layout

Copy the Compose and env files to `/srv/repperoni/deploy`, install both project configs in
Webhooker, and create `/srv/repperoni/secrets/review.env` plus `production.env` as documented
in `deploy/webhooker/secrets/README.md`.

Point wildcard DNS for `*.repperoni-review.malaber.de` at Traefik. Reviews are deliberately not
hosted below the production WebAuthn RP ID.

Review apps share RP ID `repperoni-review.malaber.de`; production uses
`repperoni.malaber.de`. Reviews deliberately use a sibling DNS branch, never a production-RP
subdomain.
`APP_BASE_URL` remains the exact public origin. These must agree with any future iOS Associated
Domains entitlement.

Create two dedicated internal proxy networks and attach the Traefik container to both. This keeps
application containers off Traefik's broader shared network and prevents public egress:

```bash
docker network create --internal repperoni_traefik_external
docker network create --internal system_traefik_reviews_external
docker network connect repperoni_traefik_external <traefik-container>
docker network connect system_traefik_reviews_external <traefik-container>
```

Compose expects resolver `letsencrypt`. It runs the app as UID/GID `10001`, with a read-only root
filesystem and only `/data` plus a constrained `/tmp` writable. Keep data directories private;
do not make them world-writable. Both deployments drop all Linux capabilities, cap CPU, memory,
PIDs, and logs, and apply Traefik request-body and rate limits.

Webhooker normally runs as UID `1000` and creates review directories dynamically. Provision the
data roots with ACLs so those directories remain writable by the app, while Webhooker can read the
production database for its pre-deploy backup. Replace `1000` if the host uses another Webhooker
UID:

```bash
sudo install -d -m 0700 -o 10001 -g 10001 /srv/repperoni/data/production
sudo install -d -m 2770 -o 1000 -g 10001 /srv/repperoni/data/reviews
sudo install -d -m 0700 -o 1000 -g 1000 /srv/repperoni/data/backups
sudo setfacl -m u:10001:rwx,d:u:10001:rwx,d:m:rwx /srv/repperoni/data/reviews
sudo setfacl -m u:1000:r-x,d:u:1000:r-x,d:m:r-x /srv/repperoni/data/production
```

## Operations and recovery

Monitor `https://repperoni.malaber.de/health/version`, not only `/health`; alert when the expected
40-character revision is missing or changes unexpectedly. Also alert on container restart loops,
filesystem exhaustion, TLS expiry, and Webhooker reconciliation failures. Keep host and Webhooker
logs outside the app container.

Webhooker makes a SQLite backup before production replacement and retains three copies. Copy
those backups off-host; three local files are rollback convenience, not disaster recovery.
Exercise this restore procedure before launch and after schema changes:

1. Stop the production Compose project so SQLite has no writers.
2. Copy the current database aside without overwriting it.
3. Validate the selected backup with `PRAGMA integrity_check`.
4. Restore it as `/srv/repperoni/data/production/repperoni.db`, owned by `10001:10001` and mode
   `0600`.
5. Start the exact previously deployed `sha-<full-sha>` image and verify `/health/version`, login,
   and one read-only workout-history request before reopening traffic.

Changing `SECRET_KEY` invalidates every browser session and bearer token. Treat that as a planned
global logout, then rotate the host env file atomically and redeploy.
