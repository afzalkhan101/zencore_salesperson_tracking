# ZenCore Field V33 — 500 m GPS Gap Display

This release is based on V32, including its Customer Management and Self Registration features. Only the mobile Live Map and Odoo Movement Map rendering are changed.

## Display rules

- A GPS recording gap between accepted consecutive segments of **500 m or less** (straight-line Haversine distance between the last recorded fix and the first resumed fix) displays as a **solid blue 8 px** connector.
- A gap of **more than 500 m** displays as a **small amber dotted** connector.
- Exactly **500 m** is solid blue.
- Both are **estimated straight-line visual links**; they do not establish actual travelled roads and are not included in measured GPS distance or totals.
- The marker artwork, GPS recording/sync data, customer workflows, and Odoo Dashboard live-position markers are unchanged. The Dashboard Live Map does not render historical route segments.

## Install Odoo 19

1. Back up the staging database.
2. Replace `zencore_salesperson_tracking` from `odoo_addon` in your Odoo.sh custom addons Git repository.
3. Push staging and upgrade **ZenCore Salesperson Tracking**. New source manifest: `19.0.11.0.20`.
4. Hard-refresh browser assets and open a salesperson Movement Map.

The Odoo Bridge remains V32; no bridge upgrade is necessary for this display-only change.

## Run Android

```bash
cd ZenCoreFieldFull
nvm use 22
npm install
npx expo install --check
npx tsc --noEmit
adb devices -l
npx expo run:android --device 4PU8QGBUOFFYGUH6
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

Do not uninstall/clear Android app storage if GPS/photo records remain unsynced.

## UAT cases

1. Two accepted route segments with a 200 m gap: solid blue connector (not dotted).
2. Exactly 500 m: solid blue connector.
3. 501 m, 800 m or 2 km gap: amber dotted connector.
4. Both styles shown in the same route with multiple gaps.
5. GPS distance must not include any visual gap connector.
6. Verify Mobile Live Map and Odoo Movement Map show matching behavior.
7. Verify customer management, registration/login, tracking, GPS queue and photos.

Caveat: Haversine threshold measures straight-line displacement, not path/road distance. For gaps with no fixes, the route travelled is unknown.
