#!/usr/bin/env bash
set -euo pipefail
package_dir=$(cd "$(dirname "$0")/.." && pwd)
version=${1:?marketing version required}
build=${2:?build number required}
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$build" =~ ^[1-9][0-9]*$ ]] || exit 2
release_dir=$(mktemp -d "${TMPDIR:-/tmp}/repperoni-testflight.XXXXXX")
auth=(-allowProvisioningUpdates)
if [[ -n "${ASC_KEY_PATH:-}" ]]; then
  : "${ASC_KEY_ID:?required with ASC_KEY_PATH}"
  : "${ASC_ISSUER_ID:?required with ASC_KEY_PATH}"
  auth+=(-authenticationKeyPath "$ASC_KEY_PATH" -authenticationKeyID "$ASC_KEY_ID" -authenticationKeyIssuerID "$ASC_ISSUER_ID")
fi
cd "$package_dir"
xcodegen generate
# Xcode must use Apple system helpers, especially rsync during IPA export.
xcodebuild_bin=$(command -v xcodebuild)
env PATH=/usr/bin:/bin:/usr/sbin:/sbin "$xcodebuild_bin" -project RepperoniApp.xcodeproj -scheme Repperoni \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$release_dir/Repperoni.xcarchive" \
  DEVELOPMENT_TEAM=VWKG94374J PRODUCT_BUNDLE_IDENTIFIER=de.malaber.repperoni \
  MARKETING_VERSION="$version" CURRENT_PROJECT_VERSION="$build" CODE_SIGN_STYLE=Automatic \
  "${auth[@]}" archive
env PATH=/usr/bin:/bin:/usr/sbin:/sbin "$xcodebuild_bin" -exportArchive -archivePath "$release_dir/Repperoni.xcarchive" \
  -exportPath "$release_dir/export" -exportOptionsPlist "$package_dir/ExportOptions.TestFlight.plist" \
  "${auth[@]}"
echo "TestFlight upload accepted. Archive: $release_dir/Repperoni.xcarchive"
