#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
node -e 'if(Number(process.versions.node.split(".")[0])<22){console.error("Node 22.13+ required; run nvm use 22");process.exit(1)}'
command -v java >/dev/null || { echo 'Install OpenJDK 17 first'; exit 1; }
command -v adb >/dev/null || { echo 'Android platform-tools / adb missing'; exit 1; }
if [ ! -d "${ANDROID_HOME:-$HOME/Android/Sdk}" ]; then echo 'ANDROID_HOME does not point to an SDK'; exit 1; fi
printf '\n[1/5] Installing declared dependencies...\n'
npm install --no-audit
printf '\n[2/5] Aligning Expo versions...\n'
npx expo install --fix
printf '\n[3/5] Checking types...\n'
npx tsc --noEmit
printf '\n[4/5] Checking Expo configuration...\n'
npx expo config --type public >/dev/null
printf '\n[5/5] Checking SDK doctor...\n'
npx expo-doctor || echo 'Review Expo Doctor notices before release.'
printf '\nSetup complete. For a fresh native build: npx expo prebuild --platform android --clean && npx expo run:android --device\n'
