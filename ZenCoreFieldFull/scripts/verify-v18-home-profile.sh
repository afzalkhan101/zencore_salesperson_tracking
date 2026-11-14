#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
grep -q 'ZENCORE_FIELD_V18_HOME_PROFILE_REDESIGN' App.tsx
grep -q 'TrackingPulse' App.tsx
grep -q 'Customers Visited' App.tsx
grep -q "{tab==='Map'" App.tsx
grep -q 'fieldProfile' src/services/odoo.ts
grep -q 'field_dashboard_v18' odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
grep -q 'Sign Out' App.tsx
python3 -m py_compile odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
printf 'V18 structural checks passed. Run npx --no-install tsc --noEmit for full typecheck.\n'
