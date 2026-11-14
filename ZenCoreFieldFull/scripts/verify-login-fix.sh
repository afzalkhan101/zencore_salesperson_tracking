#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo 'Expected v4 source marker:'
grep -n 'ZENCORE_TRANSPORT_V4_NO_COOKIE_MODULE' src/services/odoo.ts
echo 'Banned cookie imports in active source:'
if grep -R -nE "@react-native-cookies/cookies|@preeternal/react-native-cookie-manager" src App.tsx; then
  echo 'ERROR: old cookie module import remains'; exit 1
fi
echo 'Direct response.json calls in active source:'
if grep -R -nE 'await [a-zA-Z_]+\.json\(' src; then
  echo 'ERROR: direct response.json call found'; exit 1
fi
printf 'Static transport checks passed. Run npx tsc --noEmit and an Android build locally.\n'
