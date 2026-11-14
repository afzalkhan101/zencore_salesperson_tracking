#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo 'Checking V16 source markers and required endpoints...'
grep -q 'ZENCORE_FIELD_V16_LIVE_METRICS_AUTO_SWITCH' App.tsx
grep -q 'trackingMetrics' src/services/storage.ts
grep -q 'triggerAutoSync(true)' src/services/location.ts
grep -q "plans/<int:plan_id>/switch" odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
grep -q 'customer_locations' odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
if grep -q 'Switch Visit Plan Tracking' App.tsx; then echo 'Unexpected confirmation prompt'; exit 1; fi
python3 -m compileall -q odoo_addon/zencore_field_mobile_bridge
if [ -x node_modules/.bin/tsc ]; then
  node_modules/.bin/tsc --noEmit
  echo 'Full local TypeScript check passed'
else
  echo 'TypeScript check NOT run: first run npm install (node_modules missing).'
fi
echo 'V16 source checks passed.'
