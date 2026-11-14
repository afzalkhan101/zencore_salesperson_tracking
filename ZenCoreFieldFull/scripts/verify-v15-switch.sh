#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
grep -q 'ZENCORE_FIELD_V15_SAFE_TRACKING_SWITCH' App.tsx
grep -q 'Switch Tracking to This Plan' App.tsx
grep -q 'Stop Previous & Start' App.tsx
grep -q 'switchPlanTracking' src/services/odoo.ts
grep -q "v5/plans/<int:plan_id>/switch" odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
python3 - <<'PYCODE'
import ast
from pathlib import Path
for path in Path('odoo_addon/zencore_field_mobile_bridge').rglob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
print('Odoo Python syntax OK')
PYCODE
if [ -d node_modules/typescript ]; then
  ./node_modules/.bin/tsc --noEmit
else
  echo 'TypeScript type-check pending: run npm install first.'
fi
printf '%s\n' 'V15 source checks passed.'
