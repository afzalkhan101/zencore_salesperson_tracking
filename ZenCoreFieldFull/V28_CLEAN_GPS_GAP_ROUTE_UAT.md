# ZenCore Field V28 — Clean GPS-Gap Map Styling

## Release scope

Based on V27 (same walking-person SVG marker). The user-selected yellow **small dotted gap** replaces the visually heavy amber dashes in two route-rendering maps:

- Mobile: `src/components/LiveRouteMap.tsx` (Leaflet WebView)
- Odoo 19 Movement Map: `zencore_salesperson_tracking/static/src/js/templates.js`

Both draw verified, contiguous GPS segments as 8px solid blue and unknown gaps as **5px rounded amber dots**, dashArray `1 11`. No guessed road route or kilometre contribution for gaps. Start/end locations still come from real coordinates. No changes to raw SQLite GPS, Odoo location logs, tracking sync, GPS quality filter, approvals, reports or photo upload. A small matching legend is shown on both maps.

**Odoo Dashboard Live Map:** continues showing individual salesperson last known positions and Active/Inactive statuses (it does not draw historical route polylines). There is no fictitious gap drawn there.

## Installation

1. Back up Odoo.sh staging DB; update only `zencore_salesperson_tracking` from `odoo_addon/` and upgrade the module; hard refresh browser cache.
2. Mobile: extract V28 full ZIP, `cd ZenCoreFieldFull`, `npm install`, `npx --no-install tsc --noEmit`, `npx expo run:android --device <adb-serial>` if native rebuild needed, then `npx expo start --dev-client --clear`.
3. Do **not** uninstall or Clear Storage: unsynced SQLite GPS and photo evidence may be lost.

## Functional tests

- With two recorded GPS segments separated by an actual recording gap, Odoo and Mobile show thick **blue** paths with tiny **yellow round dots** between endpoints. Long solid amber dashes must not remain.
- Hover/inspect the Odoo gap to see an explanation that actual route is unknown.
- Logged GPS points, GPS history, and distance totals are unchanged; missing interval is never added to KM.
- Verify multiple gaps, one-point routes, 0-point routes, offline map tiles, running/paused sessions, map zoom, start and end markers.
- Dashboard map: green animated Active / gray static Inactive markers continue to work. No new gap route overlay is expected on Dashboard.
- Regression test on Android physical phone and Odoo.sh staging before production rollout.

## Verification limits

Source syntax/static checks and ZIP integrity can pass without validating Odoo.sh registry, live OpenStreetMap tile access, or native Android rendering. Those require staging and device UAT.
