# Architecture

Repperoni is one FastAPI process with two deliberately separate surfaces. The Jinja web routes
serve a shell, static assets, and passkey pages. The versioned JSON API owns all workout state and
is the contract for both the vanilla browser client and a future iOS application.

Authentication comes from `fastpasskey`. Repperoni implements only its persistence/session
protocol over `User`, `Passkey`, and `AuthSession`; WebAuthn generation, verification, browser
serialization, and passkey management stay in the shared package. Browser requests authenticate
with a signed cookie backed by a revocable database session. Native requests use the JWT bearer
token returned by `/api/v1/auth/login/verify`.

The workout aggregate is:

```text
User -> Workout -> WorkoutStation -> SetEntry
                         |
                      Exercise
```

Global catalog exercises have no owner; custom exercises belong to one user. Workouts, stations,
sets, last-performance lookups, and statistics are always constrained by the authenticated user.
Set mutations may carry `client_mutation_id`, allowing a future offline native client to retry a
write without creating duplicates.

SQLite is the zero-configuration default. Async SQLAlchemy keeps request handling portable, while
Alembic uses a synchronous migration driver and upgrades to head before the app accepts traffic.
The initial migration includes auth and user ownership instead of retrofitting isolation later.
