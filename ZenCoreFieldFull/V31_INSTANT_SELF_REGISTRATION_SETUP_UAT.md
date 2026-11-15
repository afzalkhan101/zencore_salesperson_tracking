# ZenCore Field V31 — Instant Salesperson Self-Registration (Odoo 19)

## Scope
- New user on Mobile: Odoo HTTPS URL + Database + Full Name + Email + Phone + Password + Confirm Password.
- Self-registered accounts are **always Salesperson**, regardless of any malicious role field. CEO, Manager, Supervisor cannot be self-assigned.
- No manager/CEO approval is needed to **create the user account**. After creation the user signs in normally.
- Existing Visit Plan approval and hierarchy are **not bypassed**.
- Forgot Password remains Odoo `/web/reset_password` (needs auth_signup / working outgoing email).
- Previous registration requests remain as historical records. New users are created immediately, not placed in the pending queue.

## Before testing (Odoo.sh staging)
1. **Back up staging**. Upload the `zencore_field_mobile_bridge` addon from `odoo_addon/` or the bridge-only ZIP and update the existing addon in your repository. `zencore_salesperson_tracking` remains the same version from V29.
2. Push changes and **Apps → ZenCore Field Mobile Bridge → Upgrade**. New bridge version `19.0.15.0.0`.
3. Self-registration is enabled by the mobile bridge route in this deployment; no System Parameter toggle or per-user approval is required.
4. Optionally set `zencore_field_mobile_bridge.default_supervisor_user_id` to the integer ID of a supervisor belonging to the same Odoo company. If exactly one eligible supervisor exists, the backend auto-assigns that supervisor even without this parameter. If there are several, an Admin/Manager must configure reporting later; new account creation/login still works, but manual Visit Plan submission may require a supervisor.
5. **Security:** Opening registration on an Internet-facing Odoo URL lets anyone who knows your URL and database name create a real internal Salesperson user. Internal Odoo licenses/seats may be consumed; email ownership is NOT verified. For production, use email OTP/invitation and stronger IP/account rate limiting, or leave registration OFF.

## Android app
```
nvm use 22
npm install
npx tsc --noEmit
adb devices -l
npx expo run:android --device 4PU8QGBUOFFYGUH6
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```
Do NOT uninstall the current app or clear storage: unsynced GPS/photo data can be lost.

## Acceptance tests
1. New email, name, valid phone, matching non-empty password (including `123`) → generic confirmation → user can sign in immediately; `res.users` shows a new active **Salesperson** account.
2. Odoo user has only `base.group_user` + field Salesperson group, not CEO/Manager/Supervisor or System Administrator.
3. User can create personal Visit Plan, select customers, and upload GPS/photos under own account. Starting GPS still requires an approved plan.
4. A second registration with the same email does not create a second user or change the original password. The response is intentionally generic to avoid account enumeration.
5. Wrong password / mismatched confirm / invalid email / bad phone / non-HTTPS URL / incorrect database → safe error, no user created.
6. `requested_role=ceo` sent directly to the API → rejected; role remains salesperson-only.
7. Registration disabled via System Parameter → HTTP 403 and no user created.
8. Without an assigned supervisor, account creation/login works but manual plan approval may be blocked; configure superior via Odoo or use existing auto-approval policy. Do not silently bypass plan approval.
9. Existing user login, forgot password, older tracking and GPS offline queue continue to work.
10. Verify that server logs and registration audit do not store passwords. Validate duplicate signup race and request rate cap under load before production.

## Validation limits
Source syntax/XML ZIP checks can pass here; Odoo.sh live registry, SMTP and real-device login must be checked in staging. This is not a production security penetration-test result.
