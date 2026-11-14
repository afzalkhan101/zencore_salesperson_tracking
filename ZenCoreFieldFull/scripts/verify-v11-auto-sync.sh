#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
grep -q 'startAutoSync' App.tsx
grep -q 'triggerAutoSync' App.tsx
grep -q 'NetInfo.addEventListener' src/services/autoSync.ts
grep -q "AppState.addEventListener" src/services/autoSync.ts
grep -q 'setInterval' src/services/autoSync.ts
grep -q 'response.accepted' src/services/sync.ts
! grep -q 'Sync GPS Now' App.tsx
! grep -q '@react-native-cookies/cookies' src/services/odoo.ts
! grep -q 'expo-linear-gradient' App.tsx
python3 -m compileall -q odoo_addon
printf 'V11 source structure + Python syntax checks passed. Run npx tsc --noEmit and native device test separately.\n'
