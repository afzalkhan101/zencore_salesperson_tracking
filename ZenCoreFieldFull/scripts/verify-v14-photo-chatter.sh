#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "Checking V14 source..."
python3 - <<'PY'
from pathlib import Path
import json
root=Path('.')
assert 'expo-file-system' in json.loads((root/'package.json').read_text())['dependencies']
app=(root/'App.tsx').read_text()
assert "ZENCORE_FIELD_V14_PHOTO_CHATTER" in app
assert 'chooseAndQueuePhoto' in app and 'Visit Photos & Chatter Evidence' in app
assert 'Temporary preview only' not in app
api=(root/'odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py').read_text()
assert '/zencore/field/v5/photos/upload' in api and 'attachment_ids=[attachment.id]' in api
assert 'photo_uuid' in (root/'odoo_addon/zencore_field_mobile_bridge/models/photo_receipt.py').read_text()
assert 'CREATE TABLE IF NOT EXISTS visit_photos' in (root/'src/services/storage.ts').read_text()
print('V14 source structure OK')
PY
python3 -m compileall -q odoo_addon/zencore_field_mobile_bridge
echo 'Odoo Python syntax OK'
if [ -d node_modules ]; then
  npx tsc --noEmit
else
  echo 'TypeScript dependencies not installed: run npm install && npx tsc --noEmit'
fi
