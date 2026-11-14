# ZenCore Field V25 — Dashboard / Menu UAT (Odoo 19)

## Deployment
1. Back up the Odoo.sh staging database and preserve the existing source commit.
2. Copy `odoo_addon/zencore_salesperson_tracking` into your staging custom-addons Git branch (replace the *existing* addon; do not install as a second module).
3. Push and wait for the Odoo.sh build to pass. Apps → ZenCore Salesperson Tracking → Upgrade.
4. Hard-refresh browser assets. No mobile app rebuild is required.

## Role-aware landing page
- CEO, Manager, Supervisor: open **Salesperson Tracking** root app menu → Dashboard.
- Salesperson: open the same root → My Visit Plans; Dashboard remains hidden.
- Verify supervisor and salesperson permissions with separate logins. User must hold the corresponding ZenCore security group.

## Dashboard dates
- Today, Yesterday, This Week, This Month remain available.
- Select **Single Date**, choose date, Apply. A single date should constrain recorded visits and GPS distance to that date.
- Select **Date Range**, choose From/To, Apply. Report uses inclusive dates.
- Historical dates are not a live tracking snapshot. Live map updates only on current-day view.

## Person-wise map search
- There is **no All Salesmen header dropdown**.
- Go to today's Dashboard → Live Map → enter a salesperson's name in the map search box. Choose an authorized result. Map should focus the last recorded location and show the popup, with no dashboard reload.
- Test inactive user with last GPS position and user with no GPS position. The latter should show "location unavailable" instead of guessing.
- Search remains limited to users in the authenticated manager's reporting scope.

## Menus
- Reports contains Performance Report and Customer Reports → Customer Detailed Report.
- Settings contains Approval Configuration and Location Data → Location History / Backups. Settings is visible to CEO/Manager only.
- Supervisor still accesses Live Tracking and its movement map but not Settings. Salesperson sees Visit Plans and Live Tracking, not Dashboard or Settings.

## Regression
- Test plan approval, auto-approval toggles (all 4 roles), mobile GPS batch sync, map markers, and existing PDF/Excel reports in staging.
- Uninstall/Clear Storage on the mobile app is not needed and may erase unsynced GPS/photos.

## Known limits
- Static checks do not replace a genuine Odoo 19 registry install/upgrade, multi-user permission test, or device GPS test.
- A stopped GPS session has only a *last known* position; it is not verified current location.
