#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PYV'
from pathlib import Path
app=Path('App.tsx').read_text()
assert "Image as RNImage" in app, 'missing React Native Image alias'
assert '<RNImage source={{uri:p.fileUri}}' in app, 'preview not using RNImage'
assert '<Image source=' not in app, 'old undefined Image JSX remains'
assert 'ZENCORE_FIELD_V14_1_IMAGE_RENDER_FIXED' in app, 'incorrect runtime marker'
print('PASS: RNImage import, photo preview JSX, runtime marker')
PYV
if test -d node_modules; then
  npx tsc --noEmit
else
  echo 'Install dependencies with npm install before running npx tsc --noEmit'
fi
