# ZenCore Field V6 — Where to update & how to run (Bangla + English)

## What caused the HTTP 404?

The phone called `POST /zencore/field/v2/plans` and received HTTP 404 HTML. The prior V5 bridge controller **did define** that exact URL. Therefore an incorrect route version in source code **was not established**. The likely issue is that the Odoo instance serving `https://<your-host>` has not loaded the `zencore_field_mobile_bridge` controller (addon absent/not installed/not upgraded/incorrect database/branch or stale routing registry). A phone-side update alone **cannot** register an Odoo server route.

## Files changed in V6

1. `src/services/odoo.ts`: new app calls V3 create and GPS batch endpoints; performs an authenticated V3 health check before creating a plan; displays actionable HTTP 404 message naming the backend module and version.
2. `odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py`: introduces `GET /zencore/field/v3/health`; retains V2 plan and GPS routes while adding V3 aliases; retains existing plan-wise tracking endpoints.
3. `odoo_addon/zencore_field_mobile_bridge/__manifest__.py`: addon version `19.0.3.0.0`.

Original Odoo core tracking module stays unchanged. Manager approval still happens in the existing Odoo web UI. Mobile creates/submits; only approved, owned plans can start plan-wise tracking.

## A — Deploy Odoo addon FIRST (required)

**Odoo.sh**

1. Back up the staging database and repository first.
2. Extract ZIP; copy the folder `ZenCoreFieldFull/odoo_addon/zencore_field_mobile_bridge` (the directory containing `__manifest__.py`) into the **configured addons path** in your Odoo.sh Git repository. For example `custom_addons/zencore_field_mobile_bridge` if `custom_addons` is a configured path; your repository may use a different directory.
3. Ensure the original `zencore_salesperson_tracking` addon is installed.
4. Commit and push the addon to the **staging branch that serves the Odoo URL on your phone**. Wait for that Odoo.sh build to finish; Odoo.sh deploy/restart loads Python controller source.
5. In staging Odoo: Apps -> Update Apps List -> find `ZenCore Field Mobile Bridge` -> **Install** or **Upgrade** if already installed.
6. Check the Odoo server startup/upgrade logs for errors and confirm the addon is installed in the same **technical database** used in the mobile Profile login.
7. While signed in to that Odoo host in a browser, open `https://YOUR-ODOO-HOST/zencore/field/v3/health`. Expected JSON:

```
{"ok":true,"bridge":"zencore_field_mobile_bridge","api_version":"v3","create_plan":"/zencore/field/v3/plans","tracking":"plan-wise"}
```

If it shows **404**, do not rebuild the phone yet: fix Odoo addon deployment/database/branch. If it redirects to `/web/login`, browser session is not authenticated; log in to the same database first. A browser GET to `/zencore/field/v3/plans` is NOT the health test; create uses POST.

**Self-hosted Odoo 19**

Copy that addon into an Odoo-configured `addons_path`, restart the same Odoo server, update the Apps List and install/upgrade `ZenCore Field Mobile Bridge`. If using command line upgrade, use the correct Python environment, executable, config and database; for example (adapt paths):

```
./odoo-bin -c /path/to/odoo.conf -d YOUR_TECHNICAL_DATABASE -u zencore_field_mobile_bridge --stop-after-init
```

After successful upgrade, restart your normal Odoo service. NEVER run this against production without database backup and maintenance approval.

## B — Ubuntu Android app setup

The ZIP contains **source files, not `node_modules`, APK or an already-built native `android/` directory**. Prerequisites: Node.js 22, JDK 17, Android Studio/SDK, Android phone with USB Debugging (or emulator).

```
cd ~
mkdir -p ZenCoreFieldV6
unzip ~/Downloads/ZenCoreField_V6_Odoo_Bridge_Fix.zip -d ~/ZenCoreFieldV6
cd ~/ZenCoreFieldV6/ZenCoreFieldFull
npm install
npx expo install --check
npx tsc --noEmit
npx expo config --type public
adb devices -l
npx expo prebuild --platform android --clean
npx expo run:android --device
```

If running the newly extracted source in a different directory than your existing app, keep Android package `com.zencore.field` unchanged if you want to update the app already on the phone. `prebuild --clean` overwrites generated native code, so do not run it on a manually modified native project without backup. Once installed, for later JS-only edits use:

```
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

**Expo Go is not the correct testing target** for this native tracking build. iOS uses the same TypeScript app, but needs macOS/Xcode or correctly configured cloud build and real-iPhone testing.

## C — Mobile Odoo Login and Plan Submit

1. Profile -> Connect Odoo 19: HTTPS **root** URL of same staging host, exact technical database name, Odoo login email, Odoo password.
2. Sign In to Odoo. If this succeeds, the Odoo session itself is working; it does **not** prove companion bridge routes are deployed.
3. Visits -> + New Plan -> date, customer target lines with Odoo Customer IDs, from/to, optional expenses -> Submit to Odoo.
4. V6 checks `GET /zencore/field/v3/health` first. If missing, message explicitly tells you to deploy/upgrade backend addon. If healthy, mobile POSTs `/zencore/field/v3/plans`.
5. Manager opens Odoo existing Visit Plans view, approves that submitted plan.
6. Phone Visits -> Refresh Odoo Plans -> open Approved plan -> Start Tracking for This Plan. The backend validates ownership, approval and scheduled date.
7. Sync -> Sync GPS Now (manual in current release). Points stay linked to plan/tracker IDs.

## D — Troubleshooting

| Result | Interpretation / Action |
|---|---|
| HTTP 404 `/zencore/field/v3/health` | Server addon NOT accessible at this host/database. Deploy/update addon FIRST, review Odoo logs. |
| HTTP 404 `/zencore/field/v3/plans` although health works | Verify correct V6 bridge code deployed, module upgraded and controller routes loaded; inspect server/access logs. |
| Redirect/HTML login page | App session routing or browser user login issue; check same host/technical database/cookie handling. |
| HTTP 400 JSON error | Controller received request; inspect returned validation message; customer IDs, selection values, permissions, data. |
| Mobile still calls `/v2/plans` | Old JS bundle or old project path. Restart Metro `--clear`, verify which folder is running, then reload. |
| Submitted plan not in Odoo | Confirm same DB, owner user, and check manager's filters/access rights. |
| GPS points absent | Separate capture/SQLite/batch API issue; health check alone does not prove tracking works. |

### Diagnostic commands (run in extracted folder)

```
grep -R -n 'zencore/field/v[23]/plans' src/services/odoo.ts odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py
python3 -m compileall -q odoo_addon/zencore_field_mobile_bridge
npx tsc --noEmit
```

**Known limitations:** This is a source integration fix and was not tested against your live Odoo host or compiled into a device APK in this environment. Live map, automatic background sync, photo upload and location search are not completed by this patch. Never submit a plan repeatedly after a network timeout before checking whether the Odoo server already created it.
