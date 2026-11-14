# ZenCore Field V14 — Camera/Gallery to Odoo Visit Plan Chatter

## What changed

- Existing Odoo login, approval, Visit Plans, GPS capture and automatic GPS syncing are retained.
- Within **Visits → open an Odoo Visit Plan → Visit Photos & Chatter Evidence**, tap **Take Photo** or **Gallery**. Add visit notes *before* selecting a photo (notes are snapshotted when added).
- Photo is copied from the temporary picker URI to `FileSystem.documentDirectory` and a SQLite row is committed. It is shown as **Pending upload** until an Odoo response identifies an attachment and chatter message.
- The foreground auto-sync engine checks photo queue on network reconnect, app resume and every 30 seconds. It sends up to 3 photographs per pass; it only marks a photo uploaded after Odoo returns `attachment_id` and `message_id`. It retains the local file for preview.
- Each photo has a stable UUID; repeat POST requests use an Odoo receipt row to avoid duplicate chatter entries.
- Current v14 attaches photos to the **Visit Plan chatter**. `customer_id` is optional; photo note and plan/tracker/customer metadata are included in the chatter message.
- JPEG/PNG/WEBP images only, max 5 MB. Other formats must be converted before selection. Do not uninstall or clear app storage while evidence remains pending.

## 1. Odoo.sh deployment — REQUIRED for V14

1. Make a **staging** backup/branch. Keep the original `zencore_salesperson_tracking` module installed unchanged.
2. Copy `odoo_addon/zencore_field_mobile_bridge` into your Git custom addons folder **replacing/updating the existing companion module source**, not the original tracking module.
3. Commit and push to Odoo.sh staging. Wait for a successful build.
4. Staging Odoo → Apps → Update Apps List → **ZenCore Field Mobile Bridge** → **Upgrade**. Module version `19.0.6.0.0`.
5. Use the same Odoo hostname and database as the mobile app. Test with a non-production plan. HTTP 404 on `/zencore/field/v5/photos/upload` means the updated bridge is not deployed or routed to that DB. Do **not** test POST with an unauthenticated browser GET; endpoint requires an authenticated POST.
6. The attachment is stored as an `ir.attachment` on model `salesperson.visit.plan` and linked to a new `mail.message` in **the plan's Chatter**. The bridge's new `zencore.mobile.photo.receipt` model is stored to deduplicate uploads.

## 2. Ubuntu / Android setup

```bash
mkdir -p ~/ZenCoreFieldV14
unzip ~/Downloads/ZenCoreField_V14_Photo_Chatter.zip -d ~/ZenCoreFieldV14
cd ~/ZenCoreFieldV14/ZenCoreFieldFull
npm install
npx expo install --check
npx tsc --noEmit
bash scripts/verify-v14-photo-chatter.sh
adb devices -l
npx expo prebuild --platform android --clean
npx expo run:android --device 4PU8QGBUOFFYGUH6
```

If device ID differs, replace it with `adb devices` value. Device selector requires **Enter**, not Ctrl+C. `prebuild --clean` overwrites generated Android native code; back up any custom native edits beforehand. V14 adds the **expo-file-system** native module: rebuild/install the APK, not just restart Metro.

Then (if Metro is not already running):

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

**Do not uninstall the existing app or clear its storage**: it may contain unsynced GPS or photo evidence. Install with the same Android package name and signing key. On signing mismatch, back up data before considering reinstall. The source ZIP intentionally excludes `node_modules`, Gradle build output and signing credentials.

## 3. Android/iOS test checklist

1. Log in with valid Odoo account. Visit Plan belongs to that user. Ensure Plan is approved/in progress/completed.
2. Open the Odoo Plan in Visits; open **Visit Photos & Chatter Evidence**.
3. Enter note; take a photo or select from gallery. Verify local preview + Pending upload.
4. With mobile/Wi-Fi OFF, capture another photo; check that Pending survives app restart (not uninstall).
5. Restore network, foreground the app. Wait for automatic sync cycle. Tap **Refresh Photo Status** to immediately reload visual status if needed.
6. Verify **Uploaded to Odoo Chatter #...** appears only after server acknowledgment.
7. Odoo → Visit Plans → open same plan → Chatter: attached image and note, matching plan ID. Check Odoo attachment paperclip.
8. Retry network interruption during POST: no duplicate photo messages after UUID receipt is committed.
9. Confirm GPS tracking, customer check-in/out, plan approval, and Visit Plan submission still function.
10. On iOS, use macOS/Xcode or EAS iOS build for native testing; Ubuntu cannot run an iOS simulator.

## Troubleshooting

- **Pending forever**: confirm Odoo.sh addon upgrade to V14, log in again if session expired, then inspect photo's inline error message.
- **HTTP 404**: v5 bridge controller not deployed in active DB.
- **HTTP 400**: file too large/invalid MIME, plan not owned by signed-in user, or access validation. Read inline error.
- **App opens old UI**: stop all old Metro servers; run from V14 directory; look for `ZENCORE_FIELD_V14_PHOTO_CHATTER` in Metro log.
- **No camera**: grant runtime Camera/Media permissions in device Settings. Image picker and file system are native packages and require an Android native build.
- **White or red screen**: capture `adb logcat -d -s ReactNativeJS:E ReactNative:E | tail -100`; do not blindly delete local SQLite.

## Limitations

- Foreground automatic retry only when the app is running/foregrounded; immediate upload after force-stop or during OS background suspension is **not guaranteed**.
- Large photos and HEIC are rejected, not silently converted; choose JPEG/PNG/WEBP below 5 MB.
- Local evidence remains until explicitly managed; no automatic retention cleanup implemented.
- This feature uploads to the **Visit Plan chatter**, not to a customer (`res.partner`) chatter or an individual check-in chatter.
- Local queue does not encrypt image bytes at the application layer; protect the phone and apply organizational privacy/retention policy.
- Native Android build, live Odoo.sh tests and iOS build remain to be performed on actual devices.
