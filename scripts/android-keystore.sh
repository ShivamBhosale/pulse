#!/usr/bin/env bash
# One-time: create a local release keystore for signing the Pulse Android APK.
# Writes android/keystore/pulse-release.jks and android/keystore.properties (both git-ignored,
# mode 600). The random password is never printed. Keep both files: Android only installs
# updates signed with the same key.
set -euo pipefail
cd "$(dirname "$0")/../android"
if [[ -f keystore.properties ]]; then
  echo "keystore.properties already exists; not overwriting." >&2
  exit 1
fi
KEYTOOL="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}/bin/keytool"
mkdir -p keystore && chmod 700 keystore
umask 077
PASS="$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)"
"$KEYTOOL" -genkeypair -noprompt -keystore keystore/pulse-release.jks -storetype PKCS12 \
  -alias pulse -keyalg RSA -keysize 3072 -validity 10000 \
  -dname "CN=Pulse personal build" -storepass "$PASS" -keypass "$PASS" >/dev/null 2>&1
cat > keystore.properties <<PROPS
storeFile=keystore/pulse-release.jks
storePassword=$PASS
keyAlias=pulse
keyPassword=$PASS
PROPS
chmod 600 keystore.properties keystore/pulse-release.jks
echo "Created android/keystore/pulse-release.jks and android/keystore.properties (git-ignored)."
echo "Back up both somewhere private; you need them to install future updates over this build."
