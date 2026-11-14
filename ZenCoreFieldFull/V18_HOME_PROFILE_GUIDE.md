# ZenCore Field V18 — Home and Profile Redesign

## Scope
V17 base. Updated only Home and Profile; Visits, Tracking, Map and offline synchronization remain present.

Home: animated active tracking banner; Visit Plans, Completed Visits, Completed Customer Visits, and Total Distance from Odoo read-only API; plan progress bar. Missing server metrics display an em dash rather than fake zeros.

Profile: after authentication, shows Odoo name, role, company, login, connection and Sign Out. Before authentication, login fields are shown. Profile data is retrieved after successful login, on startup with a valid session, and during online periodic refresh.

## Backend deployment (required)
Deploy `odoo_addon/zencore_field_mobile_bridge` to Odoo.sh staging, upgrade ZenCore Field Mobile Bridge to 19.0.9.0.0. Existing salesperson tracking addon stays installed.
GET `/zencore/field/v6/profile` and GET `/zencore/field/v6/dashboard` require authenticated sessions. No passwords returned.
The dashboard uses `salesperson.tracker.total_distance_km` and `total_visited` only if those fields exist; missing metrics appear unavailable rather than invented. `total_visited` sums completed customer visits, not distinct customer identities. The distance represents stored tracker totals and may not include unaggregated GPS history.

## Ubuntu installation
Extract ZIP into a NEW folder such as `~/ZenCoreFieldV18/ZenCoreFieldFull`. Do not overwrite your only existing source or clear app storage: pending GPS/photo data may be lost.

```bash
cd ~/ZenCoreFieldV18/ZenCoreFieldFull
npm install
npx expo install --check
npx --no-install tsc --noEmit
bash scripts/verify-v18-home-profile.sh
adb devices -l
npx expo run:android --device YOUR_DEVICE_SERIAL
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

When no native dependency changed from V17, Metro can load updated JS, but rebuilding the native app is appropriate if WebView or other native dependencies differ. Use only one Metro server and ensure it runs from V18.

## Staging tests
1. Confirm V18 build tag in Metro: ZENCORE_FIELD_V18_HOME_PROFILE_REDESIGN.
2. Confirm Home banner pulses only during an actual active tracking session, and becomes static when stopped.
3. Confirm all four KPI values match Odoo API. Don't confuse completed customer visits with unique customer count.
4. Login: form disappears; Odoo user name, company, login, role, and Sign Out appear.
5. Restart: persisted authenticated session restores profile after network verification.
6. Sign Out: form appears; unsynced data remains local, but uploads wait for login.
7. Test Visits, Tracking, Map, photos and offline GPS separately to check for regressions.

Full Android/iOS build and end-to-end Odoo.sh testing are required before production use.
