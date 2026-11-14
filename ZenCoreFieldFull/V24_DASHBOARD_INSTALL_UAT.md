# ZenCore Field V24 — Dashboard install & UAT

## Deployment
1. Backup your Odoo.sh staging database and save current Git commit.
2. Copy `odoo_addon/zencore_salesperson_tracking` over the corresponding custom addon (do not remove existing persistent data).
3. Commit/push and upgrade ZenCore Salesperson Tracking in Odoo Apps.
4. Hard refresh the browser to load versioned CSS/JS assets.
5. No mobile APK rebuild is required: this release changes only the Odoo Dashboard.

## Status semantics
- Total salespersons: distinct users who have either a tracker or a Visit Plan on the chosen day within the authorized hierarchy.
- Active: has a live tracking state and GPS heartbeat within five minutes.
- Inactive: no active session or heartbeat stale (including planned-only users).
- At Customer / Moving / Idle partition Active. They are not additional people.
- Active + Inactive = Total for Today. A stopped user remains visible.
- Offline person can show last known GPS location; it is not described as their current position.
- GPS/Check-in numbers come from tracker records. Staff with plans but without trackers have zero GPS figures.

## End-to-end role test (on staging)
1. Login as CEO/Manager/Supervisor, open Dashboard Today. Salespersons cannot open the Dashboard.
2. Create a Visit Plan today for user A; do not start tracking. Confirm user A appears as Inactive, with no invented location.
3. Start tracking as user A, send GPS, refresh. Confirm Active; keep it running and move to confirm Moving/Idle/Customer subdivisions.
4. Stop tracking and confirm Inactive, but keep name and last known location.
5. Make two tracking sessions for the same user/date. Confirm the person is counted only once.
6. Search a partial name like Afzal in Map search. Click the result; map should animate to their latest known marker without page reload. If location is absent, an unavailable message appears.
7. Use All/Active/Inactive to filter map markers; selecting a person should reveal their marker.
8. Leave map zoomed in and wait through 2 automatic ten-second polls: zoom should stay unchanged.
9. Verify KPI counts: Active + Inactive = Total, and At Customer + Moving + Idle = Active.
10. Change Today/Yesterday/This Week/This Month; historical filters still work, full navigation may occur when changing period.
11. Test Supervisor cannot search or see a different supervisor's team. Direct dashboard/data URL remains role checked.
12. Confirm existing reports, Visit Plans, GPS uploads, photos and Mobile App still work.

## Known limitations
- A user absent from both Visit Plans and tracker records is not counted: this dashboard measures staff participating in the selected period, not every employee in the organization.
- Initial date-tab changes remain normal page navigation; live ten-second refresh and map selection do not reload the page.
- Odoo.sh installation, live data and real Android tracking have not been executed in the build container.
