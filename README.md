# Repperoni

Repperoni is a friendly, API-first workout tracker built for fast one-thumb data entry between
sets. It remembers what you lifted at the current station, makes repeating or nudging the last
set quick, and turns workout history into useful progress charts afterwards.

The app uses the same family of tools as Planini and Tracy: Python 3.14, FastAPI, async
SQLAlchemy, Alembic, SQLite by default, a small vanilla-JavaScript PWA, Invoke automation,
multi-architecture containers, and Webhooker review deployments. Authentication is passkey-only
through Daniel's reusable `fastpasskey` package; browser sessions and bearer tokens let the same
API serve the web app and a future iOS client.

## Quick start

```bash
./.codex/setup.sh
.venv/bin/inv migrate
.venv/bin/inv start --reload
```

Open <http://localhost:8000>. The first account is created with a passkey. WebAuthn works on
`localhost`; do not replace it with `127.0.0.1` in the browser URL.

Copy `.env.example` to `.env` when you need persistent local configuration. At minimum, replace
`SECRET_KEY` outside local development.

## Workout flow

1. Start a workout and choose a station/exercise.
2. Repperoni shows the latest weight and reps recorded for that exercise.
3. Repeat the last set or adjust weight/reps with large step controls, then log it.
4. Switch stations without ending the workout; correct or remove accidental sets in place.
5. Finish the workout and use Progress to inspect volume, estimated one-rep max, consistency,
   personal records, and per-exercise trends.

All product state is read and changed through typed `/api/v1` endpoints. Interactive API docs are
available at `/docs`, and bearer tokens returned by passkey login are suitable for native clients.
Every query and uniqueness rule is user-scoped from the first migration.

## Invoke targets

Run `.venv/bin/inv --list` for the canonical list. The important targets are:

| Target | Purpose |
| --- | --- |
| `install-deps` | Install Python and Node dependencies |
| `migrate` | Upgrade the database to Alembic head |
| `start` | Run the foreground development server |
| `start-app`, `wait-for-app`, `stop-app` | Managed local lifecycle for automation |
| `check-python` | Black, Flake8, and pytest |
| `check-js` | JavaScript unit and coverage gate |
| `browser-e2e-desktop`, `browser-e2e-mobile` | Real Chromium + virtual-passkey user journeys |
| `verify` | Full local gate matching CI |
| `docker-build`, `docker-build-test`, `docker-smoke` | Container build and black-box checks |
| `compute-version` | Stable/RC release version used by CI |

Supported operations belong behind Invoke targets so local development and CI use the same entry
points.

## Deployment

CI tests Python, JavaScript, desktop, and phone flows before publishing the immutable
`sha-<full-sha>` multi-architecture image. PR review apps are isolated at
`https://pr-<number>.pr.repperoni.malaber.de`; production is
`https://repperoni.malaber.de`. Releases promote the already-tested image rather than rebuilding
it. See [Webhooker deployment](docs/deployment/webhooker.md).

## Project layout

```text
app/api/v1/       typed JSON API and passkey routes
app/models/       user-scoped SQLAlchemy models
app/services/     auth sessions and statistics
app/web/          Jinja shell, PWA assets, vanilla JS client
alembic/          real migration history and exercise catalog seed
tests/            API, service, migration, and deployment contract tests
scripts/          environment and browser-E2E runners
deploy/webhooker/ review and production deployment bundle
```

## Character

Repperoni's spotter is a determined pepperoni-pizza slice doing reps. The generated mascot is a
text-free project asset so it works in headers, empty states, PWA icons, and future native apps.
The product palette is tomato red, near-black, warm cheese gold, and crust orange.
