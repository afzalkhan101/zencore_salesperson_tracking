# ZenCore Field V17 — Map Replaces Sync (UI-only release)

## Scope
The bottom navigation is **Home | Visits | Tracking | Map | Profile**.
Only the original Sync tab content is replaced. Home, Visits, Tracking and Profile functionality remains in place. Existing GPS collection, offline SQLite queue, automatic Odoo upload, Visit Plans, approval, check-in/out and Chatter evidence are retained.

The **Map** tab uses Leaflet 1.9.4 within react-native-webview 14.0.1, displays current device position when foreground location permission has already been granted, and draws a blue polyline from actual recorded local GPS points for the active or last tracking session. It uses the same Plan ID, Tracker ID and Session ID to scope the route. Green markers denote route start and customer location, if known. It does not invent road routes or use a routing API.

## Before build

1. Extract ZIP to a clean directory `~/ZenCoreFieldV17/ZenCoreFieldFull` (do not mix it with earlier versions).
2. Install Node >= 22.13 (Expo SDK 58 requirement). Check `node -v`.
3. Connect a real Android phone with USB debugging, and make sure `adb devices -l` shows `device`.
4. Do not uninstall the current app or clear app data: that may delete unsynced SQLite GPS and photos. A different signing certificate may prevent updating the existing installed app. Preserve data first.

## Commands on Ubuntu

```bash
mkdir -p ~/ZenCoreFieldV17
unzip ~/Downloads/ZenCoreField_V17_Map_Replaces_Sync.zip -d ~/ZenCoreFieldV17
cd ~/ZenCoreFieldV17/ZenCoreFieldFull
npm install
npx expo install --check
npx --no-install tsc --noEmit
bash scripts/verify-v17-map.sh
adb devices -l
npx expo prebuild --platform android --clean
npx expo run:android --device
```

Select CPH2667 and press Enter if prompted. `Ctrl+C` cancels the build. The `--clean` prebuild regenerates android/, so preserve custom native changes first.

Once the native app is installed, stop earlier Metro servers and run:

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

**Native rebuild is required** for a newly added `react-native-webview` native package. Simply reloading Metro cannot install it into the existing APK.

## Validation

1. Look for Metro tag `ZENCORE_FIELD_V17_MAP_REPLACES_SYNC`.
2. Bottom nav reads Home | Visits | Tracking | Map | Profile. There is no Sync tab.
3. Open Map: Leaflet/OSM map should load over internet; if location permission was granted previously, current position should be shown.
4. Start an approved Plan from Visits (unchanged workflow), move outdoors with GPS enabled, then open Map. The recorded polyline follows locally saved fixes; a first point may take time to appear. Start and current position markers should be shown.
5. Switch plans; the route should show only points from the current exact Plan/Tracker/Session, not a concatenation of prior routes.
6. Disable internet: new map tiles will not load, but background GPS points may still be recorded as before. Reconnect and verify automatic Odoo upload from the existing bridge.
7. Check Odoo Location Data and Photo Chatter separately to confirm the previous backend workflow still works.

## Limits and policy

- Leaflet JS and CSS load over HTTPS from the pinned CDN. New map tiles require internet. No API key is required.
- OpenStreetMap's free public tile service is **best-effort** and may block high-volume or noncompliant commercial use. Use a compliant hosted/self-hosted tile provider before wide production rollout. Do not prefetch bulk tiles; keep required attribution.
- iOS must be built on macOS or through a supported cloud build pipeline; Ubuntu cannot compile an iOS native app locally.
- App background sync is OS-dependent. This release does not change existing sync timings or guarantee immediate Odoo delivery.
- Full device build and live Odoo tests must be performed in the target environment. Syntax checks alone do not certify production reliability.

## Backend / Odoo.sh

**No new Odoo bridge upgrade is needed for the V17 Map-only UI change** if the existing V16 GPS APIs are already functioning. Do not overwrite the live Odoo module just to show a map. The provided addon folder is retained as a reference to the original integration.
