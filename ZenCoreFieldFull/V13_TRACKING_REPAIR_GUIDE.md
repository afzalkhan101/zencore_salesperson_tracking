# ZenCore Field V13 — Plan Tracking State Repair

## What was fixed

The earlier Tracking tab could show `Capture enabled` when Android's location task was running but no usable active Visit Plan existed locally. Pressing Stop then failed with `No active Visit Plan on this device.`

V13 considers tracking **active only if all four conditions are true**:

- Android background location task is started.
- A valid Plan ID is saved.
- A valid Odoo Tracker ID is saved.
- A nonempty tracking session ID is saved.

V13 saves these three IDs together in one SQLite record (`tracking_identity_v13`). Existing V12 tracking records are read for compatibility until a V13 session starts or recovery completes. Existing captured GPS records are not deleted by Start, Stop, or Repair.

If Android task and saved identity disagree, Tracking displays `REPAIR REQUIRED` and a **Repair Tracking State** action. Repair stops the orphan task, clears inconsistent identity, and attempts to queue a server-side stop only when an actual Plan ID is recoverable. If no Plan ID exists, check the tracker manually in Odoo.

## Install on Ubuntu

**Do not uninstall the current Android app or clear its storage** if unsynced GPS records may exist. Keep your existing package name and signing key so installing an update can retain app storage.

```bash
cd ~
mkdir -p ZenCoreFieldV13
unzip ~/Downloads/ZenCoreField_V13_Tracking_StartStop_Repair.zip -d ~/ZenCoreFieldV13
cd ~/ZenCoreFieldV13/ZenCoreFieldFull
npm install
npx expo install --check
npx tsc --noEmit
bash scripts/verify-v13-tracking.sh
adb devices -l
npx expo run:android --device 4PU8QGBUOFFYGUH6
```

If USB device serial is different use the ID from `adb devices -l`. Let Gradle build/install finish; do not cancel at the device selection menu. Select the device and press Enter if prompted.

If `run:android` starts Metro itself, use its server. Otherwise:

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

**Do not run Metro for another project directory simultaneously.** The Tracking tab footer should read `V13 · Tracking Repair · No Map · Auto Sync`.

## How to start tracking

1. Connect the correct staging Odoo database in Profile.
2. Open Visits; refresh Odoo Plans.
3. Open an Approved Visit Plan for today (server currently enforces visit date == today).
4. Tap **Start Tracking for This Plan**.
5. Grant precise foreground and background location permissions as requested.
6. App verifies that Odoo returned a positive Tracker ID and `is_tracking: true` before starting GPS.
7. Go to Tracking. Confirm `Device State: Healthy / Recording`, Active Plan ID and Odoo Tracker ID are populated.
8. Walk outdoors with location ON. Inspect captured point count and pending queue. A first GPS fix is attempted immediately; GPS updates are not guaranteed at fixed intervals by the OS.

## How to stop tracking

1. Open Tracking > **Stop Plan Tracking**.
2. Confirm **Stop Tracking** in the dialog.
3. The app writes a pending Odoo-stop intent, stops native GPS capture, and clears the active session.
4. Pending GPS points remain in local SQLite, even offline.
5. On reconnect / app resume, V11/V12 Auto Sync uploads GPS batches; only acknowledged UUIDs become synced. Then it attempts the Odoo stop endpoint.
6. **Stop GPS != Complete Visit Plan**. Complete the plan separately in your Odoo workflow.

## How to repair the error in the screenshot

If `Device State` shows `REPAIR REQUIRED` or you previously saw `No active Visit Plan on this device`:

1. Open Tracking.
2. Tap **Repair Tracking State**.
3. It stops only an orphan/stale native GPS task and clears invalid session metadata. Existing GPS points stay in SQLite.
4. If it knew the Plan ID, it queues Odoo stop; keep internet on until `Odoo stop acknowledgement` is no longer pending.
5. If the Plan ID was missing, verify in Odoo whether the salesperson's tracker is still active and stop it there if necessary.
6. Open Visits > Approved Plan > Start Tracking again.

Do not attempt a second plan while an earlier Odoo stop acknowledgement is still pending.

## Odoo.sh deployment

**No new addon deployment is required for V13 alone** if the installed bridge already has these existing endpoints:

- `POST /zencore/field/v3/plans/<plan_id>/start`
- `POST /zencore/field/v3/plans/<plan_id>/stop`
- `POST /zencore/field/v3/gps/batch`
- `GET /zencore/field/v3/my-plans`

This update only changes the mobile application. The ZIP carries the unchanged companion addon for reference. The server must still have the compatible addon installed.

## Real-device validation checklist

- Approved Plan on today's date starts with valid Plan ID/Tracker ID.
- Android GPS notification appears; Tracking says `Healthy / Recording`.
- One captured point appears outdoors (location fix dependent).
- Stop confirmation works and stops OS location updates.
- Pending GPS remains after Stop and eventually syncs to Odoo.
- App restart restores a genuine active session, or prompts recovery when state is inconsistent.
- Starting a different Plan while tracking is active is rejected.
- Odoo Location Data shows points under the correct Tracker ID.

### Limitations

Android battery/background rules can interrupt tracking; a force-stopped application cannot guarantee continuous capture. Mobile network reconnect also cannot guarantee immediate background execution after OS suspension. A real Odoo.sh and physical-device end-to-end test is required before considering production-ready.
