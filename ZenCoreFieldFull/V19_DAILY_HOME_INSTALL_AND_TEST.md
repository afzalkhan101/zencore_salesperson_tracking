# ZenCore Field V19 — Daily Home Workspace

## Changes
- The original Home tracking hero retains its vivid blue/green background in both tracking states. Only the indicator pulse/status changes.
- Rounded KPI cards: Visit Plans, Completed Visits, Customers Visited (defaults to 0), Total Distance (defaults to 0.00 km).
- Today's Visit Progress uses today's plan target lines, not all historical plans.
- Next Customer Visit and Today's Visit Schedule are read-only and sourced from Odoo `/zencore/field/v7/home/today`. No schedule clock time is invented.
- A small network indicator replaces technical GPS-sync panels on the Home page.
- Visits, Tracking, Map, Profile and existing GPS/photo sync services are unchanged.

## Odoo.sh staging first
Deploy only `odoo_addon/zencore_field_mobile_bridge` as an update to the existing addon. Upgrade version `19.0.10.0.0`. Do not replace `zencore_salesperson_tracking`. The new endpoint is read-only and returns user-scoped planned visit targets for the current date using Odoo's contextual date.

## Ubuntu install
```bash
mkdir -p ~/ZenCoreFieldV19
unzip ~/Downloads/ZenCoreField_V19_Daily_Workspace.zip -d ~/ZenCoreFieldV19
cd ~/ZenCoreFieldV19/ZenCoreFieldFull
npm install
npx expo install --check
npx --no-install tsc --noEmit
bash scripts/verify-v19-daily-home.sh
adb devices -l
npx expo run:android --device
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```
Use this V19 folder for Metro; stop all old Metro servers before starting. Do not uninstall your old Android app or clear its data; pending SQLite GPS/photo data might be lost. Ensure matching package/signature when installing over it.

## Testing
1. Sign in; verify the profile and overall KPI data.
2. Confirm the hero stays blue-green in both active and inactive states; only the pulse changes.
3. Verify totals 0 and 0.00 km for missing/zero customer/distance data.
4. In Odoo create a plan dated today with two target lines. Verify Today's Progress = 0/2 and two schedule items.
5. Mark a target line visited using the normal Odoo workflow. Verify Progress = 1/2 after refresh, and Next Customer changes.
6. Tap Next Customer / Schedule item; verify the correct Visit Plan opens in Visits.
7. Verify tracking stop/restart, Map, camera uploads and Odoo GPS sync remain working.

Note: The new daily status uses `salesperson.visit.plan.line.is_visited`; completion requires the existing Odoo check-out/visit workflow to set this field. 'Completed Visits' in the overall KPI remains completed plans, as provided by the existing V18 endpoint. Today's schedule has no scheduled clock time because that field is not available on the Odoo target line.

## Validation
Python syntax and source assertions are checked locally. Full TypeScript, native Android/iOS and real Odoo.sh integration must pass in your environment before production use.
