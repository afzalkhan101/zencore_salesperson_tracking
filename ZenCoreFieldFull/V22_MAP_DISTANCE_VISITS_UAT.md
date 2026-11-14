# ZenCore Field V22 — Route, KM & Visits: Staging UAT

## What changed
- Odoo Movement Map: thicker 8px blue recorded route, thicker 7px yellow dashed **unknown GPS gap**; walking salesperson + briefcase marker at final recorded coordinate.
- Mobile Map: 8px blue line, 7px dashed yellow bridge only between separate *recorded* GPS segments, walking/briefcase final-position marker. Yellow is **not** a measured road route and is **not included in traveled distance**.
- Mobile Home: completed customer visits now sourced from visited lines / check-in records; visited customer count is deduplicated by partner. Total KM uses stored/verified server tracker distance and a local, read-only SQLite GPS fallback scoped to Odoo plans returned for the authenticated account. Local distance excludes GPS gaps and stationary drift.
- GPS logs, offline queue, UUID sync acknowledgements and photo evidence remain unchanged.

## Deployment
1. Backup the Odoo.sh staging database; save Git revision.
2. Update BOTH addons in your Odoo.sh custom addons path: `zencore_salesperson_tracking` (19.0.11.0.12) and `zencore_field_mobile_bridge` (19.0.12.0.0). Upgrade **Tracking** first, **Mobile Bridge** second.
3. Extract Mobile App ZIP into a fresh folder. Run `npm install`, `npx expo install --check`, `npx tsc --noEmit`, and `bash scripts/verify-v22-route-metrics.sh`.
4. With the OPPO phone connected and USB debugging enabled, run `adb devices -l`, `npx expo run:android --device 4PU8QGBUOFFYGUH6`, `adb reverse tcp:8081 tcp:8081`, `npx expo start --dev-client --clear` (after stopping any stale Metro instance).
5. **Do not uninstall or clear app storage**: pending GPS/photos can be lost.

## Test A — Route display
1. Open an existing Odoo tracker with recorded path. Check wider blue line.
2. Check yellow dashed lines only where an actual missing GPS segment exists; never assume the yellow bridge reflects streets used.
3. Confirm a walking person + bag appears on the last recorded GPS position.
4. Open Mobile Map for same plan; check similar blue line, dashed gaps and end marker.
5. Turn off internet while continuing phone GPS tracking. If GPS fixes are still recorded, **blue remains correct**. If the GPS recording itself has a time gap, it may show yellow. Restore connection; verify queue drains without deleting raw points.

## Test B — Home KM
1. Walk a real route with location permission enabled; verify the Map shows recorded coordinates. Allow Odoo sync to complete.
2. On Odoo Movement Map note 'verified GPS distance' (e.g. 0.88 km), and compare Odoo Tracker distance, Mobile Tracking tab distance, and Home Total Distance.
3. Home should show nonzero distance for accepted recorded movement, though differing data filters/sessions can produce small discrepancies; **GPS gaps excluded**.
4. Stop/restart tracking and check that Home shows summed history for owned Odoo plans, not only current tracker.
5. Login with another Odoo user on the same test device: Home local fallback must count only plans returned for that user, never other user plan IDs.

## Test C — Completed Visits
1. Begin an Approved Visit Plan; check in to a customer, then check out successfully in Odoo.
2. Wait for dashboard refresh (up to 60 seconds), or relogin. Home Completed Visits should include the completed customer visit, even when the Plan itself is not in state Completed.
3. Customers Visited counts unique checked-in partners; repeated completed visits to one customer can increase Completed Visits without increasing distinct Customers Visited.
4. A walking session alone does not complete a customer visit. The customer visit must be recorded through Odoo's check-in workflow.

## Validation limits
- Python/XML parse, Node JavaScript syntax, TypeScript/TSX syntax transpilation and ZIP integrity are checked offline.
- Actual Odoo.sh registry upgrade, React Native native build, Odoo GPS data and live routing/GPS performance **must be verified on staging and physical device**.
- These are thicker Leaflet/OSM lines, **not Google Maps SDK**. Yellow dashed segments are visual unknown-interval markers rather than a simulated travel path.
