# Repperoni for iOS

Native SwiftUI companion for iPhone and iPad, iOS 17+. Gym first: start or resume a
workout, choose an exercise, see last performance, adjust weight/reps, log a set,
and finish. Progress shows 30-day volume, streak, personal records and recent
workouts. All data uses the existing user-scoped `/api/v1` API.

Bundle ID and SKU: **de.malaber.repperoni**. Team: **VWKG94374J**.
App Store Connect: [Repperoni Workout Tracker](https://appstoreconnect.apple.com/apps/6827301454/distribution).
The short name was unavailable in Apple's global namespace. Home-screen name remains Repperoni.

## Setup and validation

Install Xcode and XcodeGen, then from the repository root:

```sh
.codex/setup.sh
.venv/bin/inv --list
.venv/bin/inv build-ios-simulator
.venv/bin/inv list-ios-simulators
.venv/bin/inv check-ios-ui --destination='platform=iOS Simulator,name=iPhone 17 Pro,OS=26.2'
.venv/bin/inv verify
```

XcodeGen creates the ignored project. `check-ios-ui` starts an isolated migrated
SQLite backend on port 8017, seeds a CLI-only user/session, bundles a temporary
fixture into the test runner, and removes it after the test. XCTest starts a
workout, adds an exercise, logs a set, relaunches to verify persistence, finishes,
and checks statistics. GitHub Actions runs this on iPhone and iPad simulators and
retains xcresult screenshots.

Native tests bypass only the OS passkey sheet using a Debug-only localhost
credential. They exercise the real API and database. Desktop/mobile browser E2E
uses fastpasskey's real virtual WebAuthn authenticator and additionally verifies
the native PKCE exchange and replay rejection. Automated tests do not claim to
exercise iCloud Keychain or Face ID.

## Authentication and deployment

Deploy migrations through `.venv/bin/inv migrate` before using this app.
Repperoni already uses the exact Malaber `fastpasskey` 0.2.6 wheel/browser module
used by Tracy. Existing users and passkeys are preserved. No WebAuthn ceremony is
copied into the app. ASWebAuthenticationSession opens the same browser passkey
flow, then exchanges a two-minute, hashed, single-use code with S256 PKCE and a
checked random state. Callback is fixed to `de.malaber.repperoni://auth`.

Tokens are stored in device-only, when-unlocked Keychain. Server sessions can be
revoked; sign-out revokes the token. Access tokens currently expire after the
server-configured period (60 minutes by default), then the app asks for another
passkey sign-in. Browser session policy is unchanged. Custom HTTPS server origins
are supported; native associated-domain entitlements are unnecessary for this
browser-based flow. Registration follows existing server policy.

Writes are confirmed only after the API succeeds. Retrying a failed set reuses
its original payload and mutation ID. This version has no persistent offline
queue: keep the app open to retry a failed save. Server-confirmed sets survive
relaunch and account sign-in.

## CLI TestFlight upload

Use an existing Xcode signing account, or set `ASC_KEY_PATH`, `ASC_KEY_ID`, and
`ASC_ISSUER_ID` to an App Store Connect API key with appropriate signing/upload
permissions. Keep keys outside this repository. A signing certificate/private key
must be available to Xcode, or cloud-managed signing must be permitted.

```sh
.venv/bin/inv upload-ios-testflight --version=1.0.0 --build-number=1
```

The script generates the project, archives Release for devices, signs using
provisioning updates, and exports directly to App Store Connect. Use a new build
number for subsequent uploads. Apple's server processing happens after upload;
this does not submit an App Store review or release the app publicly.

## Icon

`Assets.xcassets/AppIcon.appiconset/AppIcon.png` is an opaque 1024px icon generated
with the built-in imagegen tool from the existing favicon mascot. Prompt:

> Create a polished square iOS app icon derived from the reference mascot for
> Repperoni, an ironic fun gym reps tracker. Keep recognizable determined pepperoni
> pizza slice lifting a barbell, thick dark outlines, golden cheese, orange crust,
> pepperoni cheeks, cheeky tiny smile. Simplify and enlarge silhouette for tiny app
> sizes. Full bleed solid warm cream background with subtle orange halo. Center
> entire mascot and barbell with generous 10% safe margin. Premium crisp
> illustration, playful not corporate. No text, no rounded corners, no transparency.
> 1024x1024.
