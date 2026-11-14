#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
from pathlib import Path
import ast,re,xml.etree.ElementTree as ET
for p in Path('odoo_addon').rglob('*.py'):ast.parse(p.read_text())
for p in Path('odoo_addon').rglob('*.xml'):ET.parse(p)
maptxt=Path('src/components/LiveRouteMap.tsx').read_text()
odootxt=Path('odoo_addon/zencore_salesperson_tracking/static/src/js/templates.js').read_text()
app=Path('App.tsx').read_text()
bridge=Path('odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py').read_text()
assert 'dashArray' in maptxt and 'dashArray' in odootxt
assert 'walking_salesperson_briefcase' in odootxt and 'data:image/svg+xml' in maptxt
assert 'weight:8' in maptxt and 'weight: 8' in odootxt
assert 'localDistanceForPlans' in app
assert 'completed_visits' in app and 'completed_visits' in bridge
print('V22 source contract checks passed')
PY
node --check odoo_addon/zencore_salesperson_tracking/static/src/js/templates.js
