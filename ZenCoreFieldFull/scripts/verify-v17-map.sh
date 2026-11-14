#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
node - <<'JS'
const fs=require('fs');
const app=fs.readFileSync('App.tsx','utf8');
const map=fs.readFileSync('src/components/LiveRouteMap.tsx','utf8');
const store=fs.readFileSync('src/services/storage.ts','utf8');
const pkg=require('./package.json');
const checks=[
 ["V17 build marker",app.includes('ZENCORE_FIELD_V17_MAP_REPLACES_SYNC')],
 ["Map tab replaces Sync tab",app.includes("type Tab='Home'|'Visits'|'Tracking'|'Map'|'Profile'")],
 ["No Sync tab",!app.includes("tab==='Sync'")],
 ["Map component rendered",app.includes('<LiveRouteMap')],
 ["Leaflet version pinned",map.includes('leaflet@1.9.4')],
 ["OSM attribution",map.includes('© OpenStreetMap contributors')],
 ["Recorded GPS scoped to one session",store.includes('WHERE plan_id=? AND tracker_id=? AND session=?')],
 ["WebView dependency",Boolean(pkg.dependencies['react-native-webview'])],
 ["Automatic sync preserved",app.includes('startAutoSync(')],
 ];
for(const [label,ok] of checks)console.log(`${ok?'PASS':'FAIL'} ${label}`);
if(checks.some(x=>!x[1]))process.exit(1);
JS
if [ -d node_modules/typescript ]; then
  ./node_modules/.bin/tsc --noEmit
else
  echo 'TypeScript dependency not installed. Run npm install and npx --no-install tsc --noEmit on Ubuntu.'
fi
