# Webhooker deployment

Repperoni follows the same tested-image contract as Planini and Tracy:

1. CI runs Python, JavaScript, desktop browser, and mobile browser tests.
2. Only after all checks pass, CI publishes a multi-architecture image as
   `ghcr.io/malaber/repperoni:sha-<full-sha>`.
3. An internal pull request receives the alias `pr-<pr>-<sha7>` and a signed synthetic
   `pull_request` wake event.
4. Webhooker deploys it to `https://pr-<pr>.pr.repperoni.malaber.de` with isolated SQLite.
   The workflow waits for health and runs mobile E2E before posting the URL.
5. Successful main CI promotes that exact manifest to a semantic version and `latest`, then
   sends the signed production wake. Releases never rebuild application code.

## Repository configuration

Create variable `WEBHOOKER_REVIEW_WAKE_URL`, variable `WEBHOOKER_PRODUCTION_WAKE_URL`, and
secret `WEBHOOKER_WEBHOOK_SECRET`. Fork pull requests intentionally do not deploy.

## Host layout

Copy the Compose and env files to `/srv/repperoni/deploy`, install both project configs in
Webhooker, and create `/srv/repperoni/secrets/review.env` plus `production.env` as documented
in `deploy/webhooker/secrets/README.md`.

Review apps share RP ID `pr.repperoni.malaber.de`; production uses `repperoni.malaber.de`.
`APP_BASE_URL` remains the exact public origin. These must agree with any future iOS Associated
Domains entitlement. Compose expects `system_traefik_external` and resolver `letsencrypt`.
