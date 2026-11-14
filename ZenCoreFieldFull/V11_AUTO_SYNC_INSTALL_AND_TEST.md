# ZenCore Field V11 — Automatic Offline-to-Online GPS Sync

## What changed

- `src/services/autoSync.ts` (new): NetInfo online transition, app foreground/resume, and 30-second foreground queue checks. Single sync in-flight, exponential retry (15 seconds to 5 minutes), and visible status.
- `src/services/sync.ts`: sends GPS in 100-item batches (up to 10 per pass); confirms IDs individually before marking SQLite records synced. Unknown, rejected, or unacknowledged points remain pending.
- `App.tsx`: starts/stops the controller with the application, shows **Automatic Sync** status and last successful attempt, removes the manual **Sync GPS Now** control, refreshes Odoo Visit Plan statuses after reconnect and every minute while online.
- `src/services/odoo.ts`: does not clear the locally stored login marker on transient network exceptions; actual session must still be verified before upload.

**No new native dependencies.** Existing Odoo GPS batch API is unchanged. This is a V10 UI + V11 sync source release, not a production-tested Android or iOS binary.

## Installation on Ubuntu

1. Back up your existing working project. **Do not delete your installed app** or its app data: that could erase pending GPS points.
2. Extract the ZIP into a new directory, for example:

```bash
mkdir -p ~/ZenCoreFieldV11
unzip ~/Downloads/ZenCoreField_V11_AutoSync.zip -d ~/ZenCoreFieldV11
cd ~/ZenCoreFieldV11/ZenCoreFieldFull
```

3. Check prerequisites (Node 22+, JDK 17, Android SDK, ADB) and install packages:

```bash
node -v && java -version && adb devices
npm install
npx expo install --check
npx tsc --noEmit
bash scripts/verify-v11-auto-sync.sh
```

4. Only one Metro process should use 8081. Stop earlier processes from their terminals (`Ctrl+C`), and start from the **V11 directory**. A TypeScript/JS-only change normally does not require rebuilding the native APK *if* the existing installed development build has all the same native dependencies and package ID. For a clean installation:

```bash
npx expo prebuild --platform android --clean
npx expo run:android --device
# Select CPH2667 using arrow keys and ENTER if prompted; do not cancel.
```

5. Development Metro:

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

Launch **ZenCore Field** on the phone; not Expo Go. Confirm the V11 app's Sync tab shows `Automatic Sync` and no mandatory manual upload button.

## Odoo.sh addon requirement

**No new backend deployment for V11** if your existing `zencore_field_mobile_bridge` already implements `POST /zencore/field/v3/gps/batch` and responds with `{ok:true, accepted:[pointUuid...], rejected:[{id,reason}...]}`. The included addon is **reference source, not an obligatory upgrade**. If that endpoint is missing, deploy/upgrade the companion addon on Odoo.sh *staging* first. Keep the original salesperson tracking module installed.

## Real phone test — exact expected behavior

1. Sign in to the Odoo 19 staging instance from Profile; verify Visit Plans load.
2. Open an Approved Visit Plan and select **Start Tracking**. Grant foreground/background location permissions. Move with the phone until **Pending GPS** increases.
3. With app in foreground, disable Wi-Fi and mobile data. GPS points should continue to be inserted in local SQLite if permissions and location service allow. `Sync` shows **OFFLINE** and pending increases.
4. Re-enable internet while app is open. `Sync` should show **SYNCING**, then **UP TO DATE** after server acknowledgement. Pending should fall without clicking an upload button.
5. Repeat with airplane mode, then restore connectivity and reopen/resume the app. Observe automatic retry and Odoo Location Data under the correct Plan/Tracker ID.
6. Simulate Odoo server unavailable/network loss during upload: records without acknowledgement must remain pending. Restart the app and confirm they are still queued.
7. Have a Manager approve a submitted plan in Odoo; while the app remains online the Visits list should refresh automatically within about a minute (or upon reconnect).

## What this release does NOT guarantee

- **When the app is force-stopped, terminated, or suspended** mobile operating systems may prevent execution. The next app resume triggers a queue scan. Immediate background sync upon connectivity return is not guaranteed by React Native timers/NetInfo.
- Only **GPS points** are stored in the upload queue and automatically delivered. Local Visit Plan drafts are still intentionally submitted by the salesperson, and online check-in/out/photo operations have **not** been converted to offline queues.
- Odoo bridge rejects GPS points older than seven days and validates ownership and plan state. Such points stay queued and appear as sync errors until resolved; do not delete them blindly.
- Last successful sync means the server acknowledged the processed batch, not that GPS capture is continuous or that a live map exists.
- Pending SQLite data is local to the app installation; uninstalling or clearing app storage can erase it.

## If sync doesn't run

```bash
cd ~/ZenCoreFieldV11/ZenCoreFieldFull
npx tsc --noEmit
adb devices -l
adb logcat -d -s ReactNativeJS:E ReactNative:E | tail -100
```

Check Profile sign-in, Odoo URL, network reachability, GPS permissions, and `/zencore/field/v3/gps/batch` endpoint. Never paste passwords or session cookies into support logs.
