# ZenCore Field V7 — Customer Picker Fix (Odoo 19)

## Changes
- `src/services/odoo.ts`: switches customer lookup from legacy `/mobile/api/partners/search` to `/zencore/field/v3/customers`.
- `App.tsx`: tapping the customer input opens a scrollable list of the first 50 Odoo contacts. Search by name, phone, or email; debounced search, select by true `res.partner.id`, and `Load More Customers` pagination.
- `odoo_addon/zencore_field_mobile_bridge/controllers/mobile.py`: adds paginated GET `/zencore/field/v3/customers`, with database-field-aware filtering. It never references `res.partner.mobile` unless that field exists.
- Odoo's existing Salesperson Tracking module and approval workflow are unchanged.

## Important
The customer picker returns **active Odoo contacts readable by the current login**, including contacts that may not have `customer_rank > 0`. This avoids hiding valid customer records. If access rights block reading Contacts, assign the relevant Odoo access role; do not disable record rules.

## Odoo.sh staging update (required)
1. Keep `zencore_salesperson_tracking` installed; do NOT replace it.
2. Deploy the **entire** `odoo_addon/zencore_field_mobile_bridge` addon folder from this release to the configured Odoo.sh addons path, overwriting the previous bridge code.
3. Commit + push to your *staging* branch; wait for successful Odoo.sh build.
4. In staging Odoo Apps, Update Apps List and **Upgrade** ZenCore Field Mobile Bridge (version `19.0.4.0.0`).
5. Verify the V3 health endpoint still returns JSON and that customer endpoint is accessible in an authenticated browser session.

Health: `https://YOUR-ODOO-HOST/zencore/field/v3/health`
Customer list: `https://YOUR-ODOO-HOST/zencore/field/v3/customers?limit=10&offset=0`
Customer search: `https://YOUR-ODOO-HOST/zencore/field/v3/customers?q=Pizza%20Hut&limit=50`
Expected shape: `{ "ok": true, "partners": [{ "id": 123, "name": "Pizza Hut" }], "has_more": false, "next_offset": 1 }`
Never publish real customer details or session cookies in support logs.

## Mobile app — Ubuntu
Extract this ZIP into a NEW folder (do not run Metro from the old `~/ZenCoreFieldFull`):
```bash
mkdir -p ~/ZenCoreFieldV7
unzip ~/Downloads/ZenCoreField_V7_Customer_Picker.zip -d ~/ZenCoreFieldV7
cd ~/ZenCoreFieldV7/ZenCoreFieldFull
nvm use 22
npm install
npx expo install --check
npx tsc --noEmit
adb devices
npx expo run:android --device
```
After the first build, use `npx expo start --dev-client --clear` for TypeScript-only changes; do not run two Metro servers on port 8081. Keep the phone attached and use `adb reverse tcp:8081 tcp:8081` as necessary.

## Mobile test
1. Profile → sign in to the *same Odoo staging host/database* as the deployed bridge.
2. Visits → New Plan → tap **Select Odoo Customer**. Up to 50 names should appear without typing.
3. Type `Pizza Hut` → select the Odoo customer from results. Verify `Selected: Pizza Hut (#ID)`.
4. Enter From/To locations → **+ Add Target Line** → `Target Lines (1)`.
5. Submit to Odoo; manager approves in Odoo; track by approved Plan ID.

## If the customer list is empty
- Test `/zencore/field/v3/customers?limit=10` in an authenticated browser.
- **404**: bridge V7 not deployed to the current host/database or Odoo registry not reloaded.
- **403 / AccessError**: user lacks readable `res.partner` records.
- **200 + empty partners**: database contains no active readable contacts, or Odoo record rules exclude them.
- A large database is paginated; tap **Load More Customers** to see subsequent groups of 50.

## Validation limitations
Python syntax was compiled and the archive checked. TypeScript type checking, Android/iOS builds, and live Odoo endpoint behavior need verification on your environment.
