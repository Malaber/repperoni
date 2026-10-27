# Testing

`inv verify` is the complete source-level local gate:

- hash-lock regeneration and drift detection
- Black and Flake8
- Python service/API/migration tests with branch coverage
- JavaScript unit tests and coverage
- locked Python/Node advisory audits plus Bandit scans
- a matching Playwright Chromium (or the installed Chrome channel on macOS)
- the full real-browser flow at desktop and phone sizes
- the container test build and production entrypoint smoke when Docker is available

Browser tests use Chromium's virtual WebAuthn authenticator through the helper shipped with
`fastpasskey`. They create a real passkey, log sets, verify the previous-performance suggestion in
a later workout, and inspect progress. Screenshots and failure details are written to
`test-results/` and uploaded by CI.

Use `inv browser-e2e-mobile` while iterating on the gym interface, or `inv check-python` for a
backend-only edit. Run `inv security-check` to query Python and Node advisory databases and scan
Python source patterns. `inv lock-deps` regenerates all hash-locked dependency files; CI rejects
lock drift. `inv docker-smoke` starts the production image with valid production security settings
and rejects a `/health/version` revision mismatch. CI always requires container tests, production
entrypoint smoke, native amd64/arm64 image scans, and SBOM generation even when local `verify`
reports that Docker is unavailable.
