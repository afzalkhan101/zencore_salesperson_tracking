# ZenCore Field V5 — Mobile Submit + Odoo Approval + Plan ID Tracking

This delivery includes (1) a React Native/Expo Android/iOS source project and (2) the companion Odoo 19 addon `zencore_field_mobile_bridge`. It does NOT replace `zencore_salesperson_tracking` or remove any Odoo web approval capability.

## Key behavior

1. Salesperson signs into Odoo in Profile (Odoo technical database name + HTTPS host + Odoo login/password). Browser Odoo approval remains available to managers.
2. Mobile **Visits > New Plan**: choose date, purpose, customers, from/to locations, expenses. **Save Local Draft** saves to SQLite. **Submit to Odoo** creates the plan in state `submitted`, assigning `user_id` to the authenticated mobile account. Customer targets are separate lines.
3. Manager uses existing Odoo **Salesperson Tracking > Visit Plans**, reviews and clicks Approve. No change to the existing approval methods/UI.
4. Mobile **Visits > Refresh Odoo Plans** reads only plans owned by this Odoo account. Open a plan with `approved` status and tap **Start Tracking for This Plan**.
5. Server verifies user ownership, manager approval, plan date is TODAY in Odoo timezone and that no other tracker is already tracking for that user. It reuses the original `action_on_track()` method to create/reuse a tracker linked to this plan and invokes tracker `action_start_tracking()`. It returns `plan_id` and `tracker_id`.
6. Android/iOS native location service starts with `trackerId`, `planId`, and a unique device session ID. Captured GPS positions are written to SQLite first, with an optional immediate first GPS fix. They are **not automatically uploaded in this version**: open **Sync > Sync GPS Now**.
7. Odoo `/zencore/field/v2/gps/batch` validates the device point's `planId` against that tracker and rejects wrong-ownership data. UUID receipts prevent duplicate processing. Legacy V4 queued points without a plan ID can be linked from their existing tracker ID if that tracker has a plan.
8. From an active plan, **Stop Tracking** stops local GPS and server session when online. **Offline Stop** cannot immediately notify Odoo; the UI warns that server may still show active. Photos are temporary previews only; maps/auto-distance and automatic sync remain future work.

**Constraints:** Only the employee's own approved plan; start allowed only on its `visit_date`; one active plan per salesperson. Android/iOS permissions and force-stop behavior can interrupt GPS; this is not an uninterrupted tracking guarantee. Staging test required.

## Ubuntu — Mobile install

Prerequisites: Node.js 22, Java 17, Android Studio SDK installed, `ANDROID_HOME` configured, physical phone with USB Debugging enabled. Project uses Expo SDK 58 and React Native 0.88.1. Native developer build required; Expo Go cannot be relied upon for this stack.

```bash
cd ~/Downloads
unzip ZenCoreField_V5_PlanWise.zip -d ~/ZenCoreFieldV5
cd ~/ZenCoreFieldV5/ZenCoreFieldFull
npm install
npx expo install --check
npx tsc --noEmit
npx expo config --type public
adb devices -l
npx expo prebuild --platform android --clean
npx expo run:android --device
```

If installed, the app opens as **ZenCore Field**. For subsequent JS changes:

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

If you prefer to keep your currently working V4 device installation or its SQLite queue, **do not uninstall the app and do not change its Android package identifier** (`com.zencore.field`). Back up the existing source first. You may copy the new `App.tsx`, `src/` files and bridge addon into your existing project and rebuild. Do not run `prebuild --clean` over manually modified native code without a separate backup.

## Odoo 19 — Server install (must precede testing Plan ID tracking)

* Use a staging database and take a backup. `zencore_salesperson_tracking` must already be installed.
* Copy `odoo_addon/zencore_field_mobile_bridge` to an Odoo custom addons path, restart Odoo/update Apps List; install or **Upgrade** `ZenCore Field Mobile Bridge` to version `19.0.2.0.0`.
* Odoo.sh: commit addon folder to your Git repository under the configured custom addons directory; update the staging branch/build, then install/upgrade via Apps. Do not expect a phone-side update alone to add endpoints on Odoo.
* Logged-in user must be the salesperson assigned to the Visit Plan. A manager approves through the original web workflow.
* Validate server routes by signing in, refreshing plans, creating/submitting, approving, starting, syncing and stopping. Calls are protected with Odoo session auth; do not expose user credentials in logs.

### Routes used

| Endpoint | Method | Role |
|---|---|---|
| `/zencore/field/v2/plans` | POST | Mobile plan creation and optional submission |
| `/zencore/field/v3/my-plans` | GET | Own plans including approval/tracker status |
| `/zencore/field/v3/plans/<id>/start` | POST | Validate approval, date, ownership; activate tracker |
| `/zencore/field/v3/plans/<id>/stop` | POST | Stop that plan's tracker |
| `/zencore/field/v2/gps/batch` | POST | UUID-idempotent GPS upload with plan/tracker validation |

All `v3` routes require the *upgraded* companion addon; the original Odoo module alone will not have them.

## Acceptance test

1. Phone: Create a plan with two target customers, Transport=100, Food=50, Other=10. Submit. Confirm Odoo shows one plan, two target lines, Total Cost=160 and Submitted state.
2. Open Submitted plan in app: no enabled Start button. Click Approve in Odoo. Refresh mobile plans: Approved, correct salesperson and plan ID.
3. Start Approved plan **on its scheduled date**. Confirm Odoo tracker `plan_id` matches the approved plan ID, tracker is tracking and app shows active plan/tracker IDs.
4. Move outdoors with GPS enabled, Sync page should show pending points. Turn internet off, move for a period, then reconnect and press Sync GPS Now. Confirm matching `tracker_id` and `tracked_at` in Odoo Location Data.
5. Stop, then create/approve another plan and test its tracking separately. No cross-plan contamination; no simultaneous trackers for one salesperson.
6. Reject a plan and attempt start: server rejects; wrong-user plan URL must also reject.
7. Repeatedly sync the same UUID: only one Odoo receipt/log should be created.

## Known limits / unresolved production gates

- No true live map; no location autocomplete/auto planned road distance.
- Manual GPS sync only. No always-on background queue flush; OS may suspend or terminate GPS collection.
- Photo evidence is only local temporary UI preview (no durable storage/Odoo upload).
- Session cookie transport uses native fetch cookie behavior and requires device-level validation; future production authentication should use a server-validated revocable mobile token, designed and audited separately.
- `action_on_track()` and `action_start_tracking()` are inherited from the original Odoo module; Odoo 19 staging runtime verification is required.
- This package does not disable web-based plan creation/submission, because you explicitly asked to keep existing Odoo functionality unchanged. Mobile is the salesperson's intended submission interface.
