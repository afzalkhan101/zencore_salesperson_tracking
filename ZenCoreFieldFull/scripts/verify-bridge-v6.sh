#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo '[1/4] Checking V3 client endpoints'
grep -q "'/zencore/field/v3/plans'" src/services/odoo.ts
grep -q "'/zencore/field/v3/health'" src/services/odoo.ts
 echo '[2/4] Checking V2/V3 backend route compatibility'
grep -q "'/zencore/field/v2/plans', '/zencore/field/v3/plans'" odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
grep -q "'/zencore/field/v3/health'" odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
 echo '[3/4] Python syntax validation'
python3 -m compileall -q odoo_addon/zencore_field_mobile_bridge
 echo '[4/4] TypeScript check (if dependencies installed)'
if test -x node_modules/.bin/tsc; then node_modules/.bin/tsc --noEmit; else echo 'Not installed: run npm install then npx tsc --noEmit'; fi
echo 'Static bridge checks passed. Live Odoo routing and device build still require testing.'
