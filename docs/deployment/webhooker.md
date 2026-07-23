# Webhooker deployment

Repperoni follows the same tested-image contract as Planini and Tracy:

1. CI runs Python, JavaScript, desktop browser, and mobile browser tests.
2. Only after all checks pass, CI publishes a multi-architecture image as
   `ghcr.io/malaber/repperoni:sha-<full-sha>`.
3. An internal pull request receives a signed synthetic `pull_request` wake event that points
   Webhooker at that immutable `sha-<full-sha>` image.
4. Webhooker deploys it to `https://pr-<pr>.repperoni-review.malaber.de` with isolated SQLite.
   The workflow waits for health and runs mobile E2E before posting the URL.
5. Successful main CI promotes that exact manifest to a semantic version and `latest`, then
   sends the signed production wake. Releases never rebuild application code.

## Repository configuration

Create variables `WEBHOOKER_REVIEW_WAKE_URL` and `WEBHOOKER_PRODUCTION_WAKE_URL`. Store
independent `WEBHOOKER_REVIEW_WEBHOOK_SECRET` and `WEBHOOKER_PRODUCTION_WEBHOOK_SECRET`
secrets so review automation never holds the production wake credential. Fork pull requests
intentionally do not deploy.

## Host layout

Copy the Compose and env files to `/srv/repperoni/deploy`, install both project configs in
Webhooker, and create `/srv/repperoni/secrets/review.env` plus `production.env` as documented
in `deploy/webhooker/secrets/README.md`.

Review apps share RP ID `repperoni-review.malaber.de`; production uses
`repperoni.malaber.de`. Reviews deliberately use a sibling DNS branch, never a production-RP
subdomain.
`APP_BASE_URL` remains the exact public origin. These must agree with any future iOS Associated
Domains entitlement.

Create two external proxy networks and attach the Traefik container to both. Keep the review
network internal so review code cannot reach production services or the public network:

```bash
docker network create system_traefik_external
docker network create --internal system_traefik_reviews_external
docker network connect system_traefik_external <traefik-container>
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
