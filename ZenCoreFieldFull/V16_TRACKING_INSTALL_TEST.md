# ZenCore Field V16 — Real-Time GPS & Auto Switch

## Changes

- One-tap switch to another approved/in-progress Visit Plan without a confirmation modal; the **Odoo bridge** stops all of the current user's other active trackers before starting the selected tracker, under a row lock and savepoint.
- Stop attempts Odoo acknowledgment immediately after stopping native GPS (if online). Failure keeps a persisted stop intent for automatic retry. A delayed/rejected GPS upload no longer blocks Odoo stop.
- Stopped plans may be started again: when re-entering, pending stop confirmation is attempted before starting.
- Each device tracking session has a unique ID. Previous GPS points retain their original plan/tracker/session association in local SQLite.
- Each new GPS fix triggers a foreground automatic upload attempt. Offline points remain queued; only explicitly acknowledged UUIDs are marked synced. **Network and mobile OS scheduling mean instant delivery is not guaranteed.**
- Live Tracking shows GPS-estimated distance traveled for the current (or most recently stopped) session, latest reported GPS accuracy, duration of an active session, and straight-line distance to the first customer with a usable location. It does not use a map.
- Optional customer coordinates are read from `res.partner.partner_latitude` and `partner_longitude` when the fields exist. If missing/zero, show `Location unavailable`.
- All prior V15 Chatter photo attachment features are preserved.

## Crucial deployment

V16 requires an **Odoo.sh staging deploy** of `odoo_addon/zencore_field_mobile_bridge` version `19.0.8.0.0` because plan-detail now optionally returns customer coordinates. The previously deployed V15 switch endpoint remains compatible, but deploy V16 to test the full feature. Do not replace or uninstall `zencore_salesperson_tracking`. Confirm all installed Odoo module dependencies and user permissions on staging.

1. Copy `odoo_addon/zencore_field_mobile_bridge` into the Odoo.sh Git repository's recognized custom addons path.
2. Commit and push to a **staging** branch, wait for the build to succeed.
3. In Odoo staging, update Apps List if needed and upgrade `ZenCore Field Mobile Bridge`.
4. Log in with the same salesperson in the app, verify `/zencore/field/v3/health` and GET `/zencore/field/v4/plans/<id>` return JSON. Do not expose session cookies in logs.

## Ubuntu / OPPO Android

This ZIP intentionally excludes `node_modules`, `.env`, and generated Android/iOS build directories.

```bash
cd ~
mkdir -p ZenCoreFieldV16
unzip ~/Downloads/ZenCoreField_V16_Tracking_Reliability.zip -d ~/ZenCoreFieldV16
cd ~/ZenCoreFieldV16/ZenCoreFieldFull
npm install
npx expo install --check
npx --no-install tsc --noEmit
bash scripts/verify-v16-tracking.sh
adb devices -l
```

**Before installing over an existing app:** ensure any pending GPS and photo records are synced. Do not uninstall/clear storage. If the existing debug build has a different signing key, do not uninstall it without a data migration/back-up plan. Avoid more than one Metro server on port 8081.

```bash
npx expo prebuild --platform android --clean
npx expo run:android --device 4PU8QGBUOFFYGUH6
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

`prebuild --clean` regenerates the native directory; back up any native custom modifications first. Device serial may differ: inspect `adb devices`.

Verify Metro shows `[ZenCore Build] ZENCORE_FIELD_V16_LIVE_METRICS_AUTO_SWITCH`. Start Metro from **this exact V16 folder**, not `~/ZenCoreFieldFull` or a Trash copy.

## Recommended real-device staging tests

1. With Odoo online, start an approved plan. Check Odoo tracker ID, session distance/accuracy/duration and new GPS Location Data records.
2. Stop. Confirm native GPS stops; online Odoo tracker stop acknowledgment should complete without waiting for a drained GPS queue.
3. Start the **same** in-progress plan again. It should start a fresh local session; old points retain their original session ID.
4. While plan A is running, tap Start on approved plan B. No confirmation dialog should appear. Verify only B is running in Odoo and mobile, and all points keep their respective plan IDs.
5. Turn Wi-Fi/cellular off while A is recording. Local SQLite pending GPS should increase. Restore internet with app foreground; verify Odoo UUID acknowledgments and accurate plan association.
6. On the next customer: validate straight-line distance only if customer coordinates exist. Otherwise verify `Location unavailable` rather than an invented value.
7. Check Odoo's Location Data record timestamps, coordinates and accuracy; compare phone logs with timestamps. Field accuracy/distance depend on device GPS conditions.
8. Check V15 photo capture and upload to Odoo Chatter remains functional.

## Known limits and safety

- Actual near-immediate sync is **best effort** while app foregrounded. Native OS background scheduling, force-stop, no connectivity, expired sessions and Odoo processing may delay records.
- Distance traveled is filtered GPS straight-line segment accumulation; not car road-distance routing. Points with poor accuracy or unrealistic movement are excluded.
- Running timer reflects the current tracking session; stopping alone does not mark Visit Plan Completed.
- Changing native GPS state and Odoo database state cannot be globally atomic. If a network outage happens between operations, a recovery may need confirmation in Odoo. The app avoids declaring new tracking active without server confirmation.
- Changes need testing against real Odoo models and an Android development build; full live integration has **not** been verified in this build environment.
