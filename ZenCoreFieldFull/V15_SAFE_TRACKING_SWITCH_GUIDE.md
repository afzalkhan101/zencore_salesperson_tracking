# ZenCore Field V15 — Safe Tracking Switch (Odoo 19)

## What changed

When another Visit Plan is already recording, tapping **Switch Tracking to This Plan** in an approved plan opens a confirmation dialog. Confirming performs these steps:

1. Verify network, logged-in user, selected plan state, date, and pending remote stop queue.
2. Stop native GPS capture for the previous plan (its already-captured SQLite points keep their original Plan ID and Tracker ID).
3. Call `POST /zencore/field/v5/plans/<plan_id>/switch` to stop previous *Odoo trackers* and start the selected plan in a DB savepoint. A row-level lock on `res_users` serializes this user’s switch calls.
4. Start native GPS capture bound to the newly returned tracker and plan IDs.
5. Automatically synchronize pending GPS and photos. Device or server errors are reported. The app attempts compensating recovery of the previous plan if the switch fails.

**Stopping tracking does not complete the old Visit Plan.** Its `in_progress` state is left unchanged. Existing Odoo approval behavior is preserved.

## IMPORTANT: deploy backend first

This is NOT a mobile-only update. The Odoo bridge must be upgraded on the **same Odoo.sh staging database** used by the phone.

- Copy `odoo_addon/zencore_field_mobile_bridge` into the Odoo.sh project’s custom addon tree.
- Commit and push to the **staging branch**, wait for successful build.
- In Odoo Apps update list if necessary, then **Upgrade** ZenCore Field Mobile Bridge to `19.0.7.0.0`.
- Do not replace or uninstall the original `zencore_salesperson_tracking` module.
- Backend must expose `POST /zencore/field/v5/plans/<id>/switch` (authenticated). A 404 indicates wrong branch/database or missing backend upgrade.

## Run on Ubuntu (use ONE project directory)

```bash
mkdir -p ~/ZenCoreFieldV15
unzip ~/Downloads/ZenCoreField_V15_Safe_Tracking_Switch.zip -d ~/ZenCoreFieldV15
cd ~/ZenCoreFieldV15/ZenCoreFieldFull
npm install
npx expo install --check
npx --no-install tsc --noEmit
bash scripts/verify-v15-switch.sh
adb devices -l
# Stop any old Metro server on port 8081 before proceeding.
npx expo run:android --device 4PU8QGBUOFFYGUH6
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

If the hardware ID changes, use `adb devices -l` to find the current ID. Select the phone and press Enter if prompted. Do not clear the old app’s storage or uninstall it: unsynced SQLite/photo evidence may be lost. Keep package ID and signing key consistent.

For this update, JS-only changes can load through Metro, but a fresh Android build may be necessary if your installed development build is from an older native dependency set.

## Verify the running JavaScript version

The Metro console should log:

`[ZenCore Build] ZENCORE_FIELD_V15_SAFE_TRACKING_SWITCH`

You should see **Switch Tracking to This Plan** when opening an approved plan other than the active plan. If you see old strings, you are running an old project/bundle. Check `pwd`, `grep -n ZENCORE_FIELD_V15_SAFE_TRACKING_SWITCH App.tsx`, and which process owns port 8081.

## Functional acceptance test (staging)

1. Sign in as the assigned salesperson. Use two Approved plans for **today** (Odoo backend retains its planned-date requirement).
2. Open Plan A, press Start Tracking, verify the Plan ID and Tracker ID; confirm GPS point(s) captured.
3. Open Plan B. Verify **Switch Tracking to This Plan** and the confirmation naming Plan A.
4. Cancel once: Plan A must continue recording, Plan B remains not started.
5. Confirm: Plan A tracker stops, Plan B starts, mobile active Plan ID becomes B; only one Odoo tracker should have `is_tracking=True` for the user.
6. Verify the old Plan A is **not** automatically `Completed`.
7. Turn network off: already captured Plan A records remain in SQLite; Plan B’s new GPS records queue locally; switch attempts offline must be blocked.
8. Restore network while app is foregrounded. Inspect GPS batch `accepted/rejected` IDs and Odoo Location Data for correct tracker associations.
9. Test forced API failure on a staging system: do not show Plan B as recording unless the native GPS task also starts; inspect recovery messages if rollback/compensation fails.
10. Test same-plan tap (no duplicate session) and repeat switching after a successful stop.

## Limitations

- Network interruptions mid-switch are handled by best-effort compensation, **not** guaranteed distributed atomicity between Android and Odoo. If recovery fails, stop and reconcile tracker state in Odoo before retrying.
- Offline **new-plan activation** is intentionally blocked because server ownership/approval must be verified.
- Android/iOS may suspend background GPS capture or networking; app force-stop prevents guaranteed continuous capture/sync.
- Odoo.sh live integration and native Android/iOS tests are **not** validated in the source-package build environment.
