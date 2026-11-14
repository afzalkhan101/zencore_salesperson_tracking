# ZenCore Field V23 — Photo Evidence, Location & Chatter

## Deployment order
1. Back up Odoo.sh staging. Deploy and upgrade `zencore_field_mobile_bridge` 19.0.13.0.0.
2. The existing `zencore_salesperson_tracking` addon is unchanged from V22.
3. Install app dependencies (`npm install`) and run `npx tsc --noEmit`, then `npx expo run:android --device <serial>`.
4. Do NOT uninstall or clear app storage: offline GPS and photo queues are persisted in SQLite.

## UAT
- **Camera, precise location allowed and internet available**: take a photo on an approved plan; confirm Chatter shows actual uploader, reverse-geocoded location, GPS coords, device (when supported), captured timestamp, note, photo attachment, and OpenStreetMap link.
- **Camera, GPS disabled/permission denied**: app may request location access, but photo uploads, Location says Unavailable (never fabricated).
- **Camera, network offline**: photo queues in SQLite; when back online metadata persists and upload occurs once; location may show only recorded GPS coordinates if reverse geocoding unavailable.
- **Gallery image**: must NOT label the uploader's current GPS coordinates as the historical image's capture location. Shows Unavailable and 'Selected for upload'.
- **HTML injection**: use a note `<p>test & hello</p>`; rendered as literal safe text, while surrounding Odoo Chatter labels remain formatted without visible HTML tags.
- **Retry**: same UUID must return prior receipt without a duplicate Chatter message.
- **Roles**: only the owner can upload to their approved plan; attachment and message belong to the plan.
- **Old queued photos**: SQLite migrations add nullable location columns; previously queued photos upload normally with unavailable location.

## Caveats
- Reverse geocoding requires a supported native geocoder/network, and may not resolve an address. This implementation does not use the plan's From/To locations as capture evidence.
- Location on an existing gallery photo is intentionally not inferred.
- Exact display of markup depends on Odoo's Chatter HTML sanitizer; inspect it on staging.
- Live Android/Odoo.sh integration testing is still required.
