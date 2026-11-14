# ZenCore Field V27 — shared walking salesperson marker

## What changed
- One identical SVG artwork in Odoo Dashboard Live Map, Odoo Movement Map, and Mobile Live Map.
- No circular icon background and no separately rendered Unicode briefcase emoji.
- Green shirt, small briefcase held in the figure’s hand, subtle shadow only.
- Dashboard active marker retains green pulse; dashboard inactive marker is gray and static.
- Existing GPS points, routes, gap indicators, status logic, APIs and SQLite data were not changed.

## Odoo.sh staging deployment
1. Backup staging database and keep a copy of the previous module Git commit.
2. Update `odoo_addon/zencore_salesperson_tracking` from the ZIP in your repository.
3. Push staging; upgrade `zencore_salesperson_tracking` in Apps.
4. Hard-refresh Odoo (Ctrl+Shift+R) to load new static assets.
5. Check Dashboard Live Map (one active and one inactive salesperson); search by name and confirm active green pulse / inactive gray static.
6. From Live Tracking, open Movement Map and verify the SVG is at the last recorded point (not a round white badge).

## Mobile
1. In ZenCoreFieldFull: run `npm install`, `npx expo install --check`, `npx tsc --noEmit`.
2. Run `npx expo run:android --device <device-serial>` when a native rebuild is required.
3. Run `adb reverse tcp:8081 tcp:8081` and `npx expo start --dev-client --clear`.
4. On Map, verify the single person carries a small bag, with no circle. Check during active/stopped sessions.
5. Compare the artwork with Odoo Movement Map and Dashboard.

Do not uninstall or clear data in an app with un-synced GPS points or photos.
Static validation cannot prove live Odoo.sh or physical-device behavior; test in staging.
