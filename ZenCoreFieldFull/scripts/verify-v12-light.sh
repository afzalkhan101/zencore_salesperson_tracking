#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
from pathlib import Path
root=Path('.')
app=(root/'App.tsx').read_text()
assert 'Live map integration pending' not in app
assert 'GPS Capture Status' in app
assert 'getPendingStopPlan' in app
assert 'setPendingStopPlan(planId)' in app
assert 'gpsSummary' in app
assert 'react-native-maps' not in (root/'package.json').read_text()
assert 'expo-linear-gradient' not in (root/'package.json').read_text()
auto=(root/'src/services/autoSync.ts').read_text()
assert 'flushPendingPlanStop' in auto
storage=(root/'src/services/storage.ts').read_text()
assert "pending_stop_plan_id" in storage
assert (root/'odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py').exists()
print('V12 Light source structure: PASS')
PY
