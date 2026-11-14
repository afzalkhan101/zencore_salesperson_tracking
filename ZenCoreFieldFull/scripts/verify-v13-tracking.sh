#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
from pathlib import Path
app=Path('App.tsx').read_text()
loc=Path('src/services/location.ts').read_text()
storage=Path('src/services/storage.ts').read_text()
checks={
 'tracking state inspection': 'inspectTracking' in loc and 'needsRecovery' in loc,
 'atomic session identity': 'tracking_identity_v13' in storage,
 'safe stop sequence': loc.index('stopLocationUpdatesAsync(TASK)') < loc.index('await setTrackingIdentity(null);\n}') if 'await setTrackingIdentity(null);\n}' in loc else False,
 'repair UI': 'Repair Tracking State' in app,
 'stop confirmation': "'Stop Plan Tracking'" in app,
 'plan-specific remote start': 'Odoo.startPlanTracking(planId)' in app,
 'auto-sync preserved': 'startAutoSync' in app,
 'no map library': 'react-native-maps' not in app,
 'version marker': 'ZENCORE_FIELD_V13_TRACKING_STATE_REPAIR' in app,
}
for k,v in checks.items():print(('PASS' if v else 'FAIL')+' '+k)
if not all(checks.values()):raise SystemExit(1)
PY
