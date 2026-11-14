# ZenCore Field V26 — Animated Active/Inactive Walking Markers (Odoo 19)

## Scope
Odoo Dashboard Live Map only. This preserves the V25.1 role-based landing, GPS collection, Visit Plans, person-wise search, date filters, PDF reports, and mobile application source. No phone rebuild is needed.

### Expected behavior
- Active salesperson: walking person in green with a much smaller briefcase held at the hand; a green pulsing halo appears beneath the feet. Very subtle 2 px walking bob. This represents Odoo's server-confirmed current status.
- Inactive or stale heartbeat: same person rendered grayscale and completely static, retaining the last known GPS position when available.
- No location available: no fabricated point. Person remains available in roster, but not as a map marker.
- Marker popup: name, active/inactive, last update, distance, visits, GPS accuracy and movement-map link.
- Every 10-second refresh updates position/tooltip, but reuses the marker DOM when the status/name has not changed, so the pulse does not continually restart and map zoom or selection is preserved.
- Reduced-motion OS/browser setting disables animations without hiding status.

### Odoo.sh staging deployment
1. Backup the staging database and note current Git revision.
2. Copy `odoo_addon/zencore_salesperson_tracking` to your custom addons repository over the existing folder (retain your repository's other addons).
3. Commit/push to staging, wait for a successful build.
4. Open Apps, upgrade `ZenCore Salesperson Tracking` (manifest version `19.0.11.0.17`).
5. Hard refresh the browser (Ctrl+Shift+R) so asset bundles update.
6. Open Salesperson Tracking > Dashboard as Manager, CEO, or Supervisor.

### Role and map UAT
1. Start a GPS tracking session using an approved Visit Plan in the mobile app; confirm a recent Odoo GPS fix is synced.
2. On Dashboard, locate that salesperson: green walking icon + a green halo under feet. Search by their name inside Live Map, select their location, check that the map focuses and popup details match.
3. Keep Dashboard open for 30 seconds; ensure polling updates without changing zoom or restarting the marker every cycle.
4. Stop tracking; wait for backend refresh. Expect gray, stationary marker, if last known position exists.
5. Start again and sync a recent GPS fix; expect it to turn green and pulse.
6. To test heartbeat timeout, allow >5 minutes with no synced GPS updates; backend classifies status as inactive even if a session flag remains set. Do not fake GPS timestamps on production.
7. Search an inactive staff member. Map should focus their last known location if present; no location should show 'location unavailable'.
8. Test CEO/Manager/Supervisor hierarchy restrictions; no unauthorized staff GPS locations should show.
9. Use a browser/device with 'Reduce Motion' enabled: labels/colors remain, animation stops.

### Limitations / release note
The green/gray classification relies on the pre-existing backend status logic (tracking state plus GPS freshness), not a client-inferred status. A GPS point may be stale or absent if offline; maps never invent current location. CSS pulse visually indicates online recording, not guaranteed precise live position. Source static tests passed, but Odoo.sh installation and browser runtime are pending staging UAT.
