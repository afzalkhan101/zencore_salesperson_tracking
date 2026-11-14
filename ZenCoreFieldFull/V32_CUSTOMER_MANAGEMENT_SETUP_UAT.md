# ZenCore Field V32 — Mobile Customer Management (Odoo 19)

## Scope

This release builds on V31. In Profile → **Customers / Add Customer**, logged-in internal staff can:

- Search/paginate customers already visible to them in Odoo.
- Create a customer with Name, Phone, Email, Address and **verified** Latitude/Longitude.
- Search an address to locate approximate coordinates, reverse-lookup coordinates to an address, and select/drag a pin on a Leaflet / OpenStreetMap map.
- Save the customer to Odoo `res.partner` with `street`, `partner_latitude`, `partner_longitude` and the active company.
- Select the new customer later in Visit Plans. Existing plan map points read the same Odoo partner GPS fields.

No changes are made to local SQLite GPS/photo queues, tracking capture, report access, or approval logic. Customer points do **not** start salesperson tracking.

## Backend installation (Odoo.sh staging first)

1. Back up the staging database and commit the full existing custom addons to Git.
2. Update `zencore_field_mobile_bridge` from `odoo_addon/` (module version **19.0.16.0.0**).
3. This module depends on `base_geolocalize` for the `partner_latitude`/`partner_longitude` fields. Verify it is available to the staging database.
4. Push to Odoo.sh; let the build finish. Then **Apps → ZenCore Field Mobile Bridge → Upgrade**.
5. Use a role-authorized salesperson login. The endpoint is authenticated (`/zencore/field/v11/customers/create`) and creates contact records for the active company only; user cannot pass a company ID, owner, privilege group, or role.
6. No additional module is needed for Odoo's existing customer geo fields and tracking point display.

## Android installation

```bash
cd ZenCoreFieldFull
nvm use 22
npm install
npx expo install --check
npx tsc --noEmit
adb devices -l
npx expo run:android --device YOUR_DEVICE_SERIAL
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

**Do not uninstall the existing app or clear storage**: unsynced GPS or photo evidence may be present.

## Test workflow

1. Sign in to staging Odoo. Profile → **Customers / Add Customer** → **+ Add Customer**.
2. Enter `Banasree Test Store`, an optional phone/email, and a detailed real address.
3. Tap **Find Coordinates from Address**. If found, inspect the coordinates and pick the exact storefront location on the map; online tiles and geocoding are required.
4. Alternatively enter actual Latitude/Longitude → **Find Address from Coordinates** → verify/edit the returned address.
5. Save. Open Odoo Contacts and confirm same-company partner, street/address and `partner_latitude`/`partner_longitude`.
6. Start Visit Plan editing → customer picker → search the exact new name. Add it as a target. Confirm it appears on an existing Odoo customer point map when the relevant view supports points.
7. Test invalid coordinates, zero coordinates, missing name/address, duplicate email in same company, and a logged-out attempt. Expect validation or authentication denial.
8. Test another company, noninternal user and exceeding 20 new contacts per user per hour. No unauthenticated or cross-company customer creation should work.
9. Verify existing Visit Plan approval, active/inactive map markers, GPS tracking, SQLite offline sync and photo evidence still function.

## Provider limitations and accuracy

- Geocoding uses a **user-initiated** Nominatim public service request; it is not automatic on keystrokes. Requests are throttled on the device. Nominatim may reject or rate-limit lookups. Network/map tiles need internet.
- For production, configure an approved managed or self-hosted geocoding service. Public Nominatim should not be relied on for substantial multiuser traffic.
- The address returned by reverse geocoding is approximate: always verify/edit the address and map marker before saving.
- GPS coordinates are stored as entered/selected; no silent substitution or assumed Odoo default address is made.
- The bridge creates authenticated contact records using explicit allowed fields. A basic per-user volume cap is enforced. More robust organization policies and audit/rate limiting may be required before broad deployment.

## Validation boundary

Python and XML parsing, isolated React Native TSX transpilation and ZIP integrity can be checked offline. Odoo.sh upgrade, Expo native build, live geocoding and Contacts map UI are **not** demonstrated by these checks and require the staging UAT above.
