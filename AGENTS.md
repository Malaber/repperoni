# Repperoni contributor instructions

- Run `.codex/setup.sh` before other project commands.
- Use `.venv/bin/inv --list` and Invoke targets for setup, checks, servers, migrations, browser
  tests, Docker, and releases. Add a target when a supported operation is missing.
- Keep the product API-first. Browser features must call `/api/v1`; do not hide domain mutations
  in Jinja form handlers.
- Keep every domain query user-scoped and add a regression test for cross-user access.
- Use `fastpasskey` through its repository adapter. Do not copy WebAuthn ceremony code into this
  repository.
- Add or modify the Alembic history for schema changes; tests must exercise migrations.
- Run `.venv/bin/inv verify` before handing off a change. UI changes require both desktop and
  mobile browser coverage with the real virtual WebAuthn flow.
- Preserve the gym-first interaction: large targets, visible last performance, minimal typing,
  accessible labels, and no critical action that requires hover.
