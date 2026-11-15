#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo 'Checking Visit Plan parity files and routes...'
grep -q 'VisitPlanEditor' App.tsx
grep -q 'findEmployees' src/services/odoo.ts
grep -q '/zencore/field/v4/employees' odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
grep -q 'employee_ids' odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
grep -q 'customer_ids' odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
python3 -m compileall -q odoo_addon/zencore_field_mobile_bridge
if test -d node_modules; then npx tsc --noEmit; else echo 'node_modules missing: run npm install, then npx tsc --noEmit'; fi
echo 'Static checks completed.'
