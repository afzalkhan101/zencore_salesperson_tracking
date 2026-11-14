# ZenCore Field V21 — Map & Visit Plan Clean UI

## Changes
- Map: applies a view-only GPS quality filter to the route before drawing. Rejects poor fixes (>35m accuracy), stationary jitter, impossible speed jumps, one-point out-and-back spikes, and breaks lines across long recording gaps. The SQLite GPS queue and Odoo sync data are **not** changed. A filter cannot guarantee a perfectly road-aligned route without map matching and a suitable routing provider; test in a real vehicle.
- Visit Plan target: From Location and To Location are geocoded once user finishes address entry. The OSRM driving-route distance is then written to Expected KM. The Recalculate Road KM button is available for retry. The field remains editable. On errors the app displays the error and does not invent a kilometer estimate.
- Removed verbose instruction/help paragraphs from the Map, Visits, Tracking, photo evidence, and plan editor screens; functional field labels and genuine errors remain.

## Usage and limits
- This demo/testing implementation defaults to the **public** OpenStreetMap Nominatim geocoder and the OSRM demo router. These are not production SLAs and can rate-limit or fail. The app avoids autocomplete, waits 1.2s between address lookups, caches lookups in a running session, and requests geocoding only after user completes field entry. Production deployments with many salespeople should use managed/self-hosted geocoding and routing endpoints.
- Configure the endpoints at build time in `.env`:
```
EXPO_PUBLIC_ZC_GEOCODE_URL=https://your-geocoder.example/search
EXPO_PUBLIC_ZC_ROUTING_URL=https://your-router.example/route/v1/driving
```
  The geocoder must accept Nominatim-style `?format=json&limit=1&q=` and respond with `[{lat,lon,display_name}]`. The router must accept OSRM-compatible `/lon,lat;lon,lat?overview=false&steps=false` and return `code: Ok`, `routes[0].distance` in meters. No API key or secret should be placed in Expo `EXPO_PUBLIC_*` values; proxy server-side if a key is needed.
- Both geocoding and routing require internet; the manual Expected KM field remains available offline.
- OSM map tile attribution is retained inside Leaflet. Address search is NOT autocomplete.

## Run on Ubuntu / Android
1. Extract ZIP to a **new folder**; do not overwrite an older running source tree:
```
mkdir -p ~/ZenCoreFieldV21
unzip ~/Downloads/ZenCoreField_V21_MapClean_RoadDistance_FULL.zip -d ~/ZenCoreFieldV21
cd ~/ZenCoreFieldV21/ZenCoreFieldFull
nvm use 22
npm install
npx expo install --check
npx tsc --noEmit
```
2. Stop any old Metro instance. If native dependencies already match the installed development build, run:
```
adb devices -l
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```
3. If a native rebuild is needed:
```
npx expo run:android --device 4PU8QGBUOFFYGUH6
```
Do not uninstall or clear app data: local unsynced GPS/photos may be present.

## Test cases
1. Open Visits → New Plan → Target Lines. Enter `Mirpur, Dhaka, Bangladesh` and `Moghbazar, Dhaka, Bangladesh`, complete editing each input. Check Expected KM becomes positive, and edit it manually if necessary.
2. Disconnect mobile internet; edit addresses, verify the UI shows a genuine service error, not a fake distance. Confirm manually entering KM still works.
3. Open an approved Plan and start tracking in a real GPS-enabled outdoor setting. Check Map: stationary positions do not draw a star/zigzag; impossible GPS jumps are excluded. Walk/drive along a known route, compare with GPS traces, and verify route segments do not leap over long gaps.
4. Verify raw GPS points still auto-upload to Odoo, even though the display may omit rejected fixes. Verify old uploaded GPS data remains intact.
5. Visit Plan photo evidence, customer check-in/out, approvals and other tabs should behave as before.
6. Repeat map tests with weak GPS (indoor/urban canyon). Expected: brief route gaps are possible, and a true road-snapped line is **not guaranteed** without a map-matching service.

## Validation
- TypeScript/TSX transpilation syntax verified.
- GPS filter exercised on synthetic stationary jitter + teleport trace.
- Python addon compilation verified.
- Full dependency typecheck, live Android installation, real geocoding/OSRM requests, and Odoo.sh device UAT remain pending.
