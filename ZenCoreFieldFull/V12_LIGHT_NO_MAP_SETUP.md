# ZenCore Field V12 Light — No Map / Offline GPS / Auto Sync

## Scope

- Keeps the V11/Odoo 19 Visit Plan submission, existing manager approval, and plan-specific tracking routes.
- Removes the mobile map placeholder and does not add Google Maps, react-native-maps or an API key.
- The Tracking screen displays Plan ID, Tracker ID, captured GPS points, pending count, last recorded GPS accuracy and fix time.
- GPS points are first saved in local SQLite with Plan ID, Tracker ID and session ID.
- Auto Sync attempts upload on network reconnect, foreground/resume, and approximately every 30 seconds while foregrounded.
- Each point is marked synced only when the Odoo bridge acknowledges its UUID.
- An offline Stop Plan Tracking action is persisted locally and sent automatically **after pending GPS uploads are acknowledged**, so location points and the stop request remain ordered.
- Plan details use the V4 bridge endpoint, avoiding the old partner mobile-field response path.

## Important constraints

1. This is source code intended for staging/real-device testing. Full Android/iOS builds and a live Odoo instance were not available in the packaging environment.
2. Android/iOS can suspend or stop location capture, notably on battery saver, permission revocation, or user force-stop. There is no guaranteed uninterrupted tracking.
3. Background network sync is not guaranteed while suspended. Pending data stays in SQLite and is retried on foreground resume.
4. A permanently rejected GPS record remains pending for investigation and can postpone Odoo stop acknowledgement. Do not clear the application's storage. Check rejection reasons and the bridge response.
5. **Stop Tracking does not mark the Visit Plan Completed.** This is a separate Odoo business action.
6. Only GPS points and queued tracker-stop requests are automatically synchronized by this release. Offline new-plan creation, photos, and customer check-ins do not have a persistent offline upload queue.

## Deploy the right component

This V12 Light release makes **no new Odoo model/controller changes**. If `zencore_field_mobile_bridge` (the V8+ compatible version) is already installed on the same Odoo 19 database, `/zencore/field/v3/gps/batch`, `/zencore/field/v3/plans/<id>/start`, `/zencore/field/v3/plans/<id>/stop`, and `/zencore/field/v4/plans/<id>` work, **do not reinstall or upgrade the Odoo.sh module for V12 Light**.

If the bridge is missing, deploy the included `odoo_addon/zencore_field_mobile_bridge` on an Odoo.sh **staging** branch, install/upgrade from Apps, and verify its routes before testing. Preserve the original `zencore_salesperson_tracking` addon. Existing `/mobile/api/checkin` and `/mobile/api/checkout/<id>` endpoints still belong to the original module.

## Ubuntu: install and build

Extract to a NEW folder, e.g.:

```bash
mkdir -p ~/ZenCoreFieldV12Light
unzip ~/Downloads/ZenCoreField_V12_Light_NoMap_AutoSync.zip -d ~/ZenCoreFieldV12Light
cd ~/ZenCoreFieldV12Light/ZenCoreFieldFull
```

Use Node.js 22+ (and the compatible Expo SDK 58 version declared in package.json), JDK 17 and the Android SDK installed with Android Studio:

```bash
node -v
java -version
echo "$ANDROID_HOME"
npm install
npx expo install --check
npx tsc --noEmit
bash scripts/verify-v12-light.sh
adb devices -l
```

On a device with **no unsynced user data at risk** or on a newly extracted project, generate the native Android project and build/install:

```bash
npx expo prebuild --platform android --clean
npx expo run:android --device 4PU8QGBUOFFYGUH6
```

Device IDs can change, so replace with the ID printed by `adb devices`. If the device selector appears, press **Enter**, not Ctrl+C. The same package ID `com.zencore.field` preserves app storage only if signing and upgrade conditions allow. Back up important data first. Do not uninstall the existing working app or clear its storage if pending GPS records are present.

Then, if a Metro server was not already started:

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

**Never run two Metro servers from different ZenCore Field folders.** To see what owns the port:

```bash
sudo lsof -nP -iTCP:8081 -sTCP:LISTEN
```

## iOS

The TypeScript source targets Android and iOS. iOS native compilation requires macOS/Xcode or an appropriately configured supported remote build service; Ubuntu cannot locally compile the iOS native target. Follow platform location permission requirements.

## Real-world test

1. Sign in from Profile to the intended Odoo 19 staging database.
2. Open Visits, refresh Plans, open an approved plan, and tap **Start Tracking for This Plan**. Check the Plan ID and Tracker ID on the Tracking screen.
3. Permit foreground and background location access; allow the foreground-service notification on Android where required.
4. With internet available, walk in an open area. Confirm captured GPS points and a plausible accuracy reading. Indoor GPS may not immediately produce a fix.
5. Turn off Wi-Fi/mobile data (leave Location ON), continue a short walk, and verify Pending GPS increases.
6. Turn internet back on while app is in foreground. Watch Sync status until point UUIDs are acknowledged. Verify those records appear in Odoo Location Data under the exact Plan/Tracker IDs.
7. Test offline **Stop Plan Tracking**. The screen must show a queued stop until points are uploaded and Odoo confirms the stop.
8. Confirm separate approved plans never mix GPS points. Do not start a new plan until the previous stop is acknowledged.

## If there is an error

- A red screen: `adb logcat -d -s ReactNativeJS:E ReactNative:E | tail -100`.
- Build failed: save the first `* What went wrong:` Gradle section.
- No GPS points: verify physical device location switch, permissions, Android battery optimization, and the Plan/Tracker IDs; check if the app was force-stopped.
- Upload rejected: inspect the Sync screen `Last Error`, bridge batch `rejected[]` reasons, and server logs. The server currently rejects GPS timestamps older than 7 days.
- Odoo plan detail 404: check V4 plan-details endpoint and installed bridge version; **changing only mobile code cannot install Odoo endpoints**.
- The visible `tracking active` label is based on local tracking task/session status; Odoo tracker state should also be checked when investigating inconsistencies.
