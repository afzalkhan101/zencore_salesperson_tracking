#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd -P)"
printf 'Project: %s\n' "$ROOT"
case "$ROOT" in *'/Trash/'*|*'/Trash/files/'*) echo 'ERROR: Do not build inside Trash.' >&2; exit 1;; esac
if [ ! -f package.json ] || [ ! -f App.tsx ]; then echo 'Wrong directory' >&2; exit 1; fi
command -v node >/dev/null || { echo 'Node.js is missing'; exit 1; }
command -v adb >/dev/null || { echo 'Android SDK platform-tools (adb) are missing'; exit 1; }
node --version
npm install
npx expo install --check
npx tsc --noEmit
bash scripts/verify-v13-tracking.sh
if [ ! -d node_modules/@react-native-community/netinfo/android ]; then
 echo 'NetInfo Android source is missing; restoring Expo-compatible package'
 npx expo install @react-native-community/netinfo
fi
test -d node_modules/@react-native-community/netinfo/android || { echo 'NetInfo native source still missing' >&2; exit 1; }
if [ -d android ]; then
 echo 'Backing up previously generated android directory (no app data on phone is removed).'
 mv android "android.source-backup.$(date +%Y%m%d%H%M%S)"
fi
npx expo prebuild --platform android --clean
printf '\nNative project created in: %s/android\n' "$ROOT"
printf 'Check connected devices: adb devices -l\n'
printf 'Build with: npx expo run:android --device YOUR_ADB_SERIAL\n'
