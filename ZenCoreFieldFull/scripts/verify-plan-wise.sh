#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
printf 'Checking app dependencies...\n'
npm ls expo expo-location expo-sqlite expo-secure-store expo-task-manager expo-image-picker @react-native-community/netinfo >/dev/null
printf 'Checking TS...\n'
npx tsc --noEmit
printf 'Checking Expo config...\n'
npx expo config --type public >/dev/null
printf 'Checking that old cookie manager is absent...\n'
if npm ls @react-native-cookies/cookies @preeternal/react-native-cookie-manager --depth=0 2>/dev/null | grep -E 'cookies/cookies|preeternal/react-native-cookie-manager'; then
  echo 'Old cookie manager detected; remove it before build' >&2; exit 1
fi
printf 'All local checks completed. Native build and live Odoo tests are separate.\n'
