# ZenCore Field V25.1 — Odoo 19 OWL landing action fix

## Root cause
`ZenCoreFieldRoleEntry.setup()` used `useService("user")`, which raises `Service user is not available` in this Odoo 19 web client. An uncaught setup exception crashes the page before role routing.

## Fix
The frontend now uses the standard Odoo `orm` and `action` services. `res.users.zc_get_field_landing_action()` resolves the landing action using the authenticated session, matching dashboard backend role rules. The frontend cannot choose a privileged role.

- CEO / Manager / Supervisor / Odoo System Administrator => Dashboard
- Salesperson => My Visit Plans

## Deploy
1. Back up your staging database and save the current commit.
2. Replace only the `zencore_salesperson_tracking` addon with the V25.1 ZIP contents.
3. Commit and push to Odoo.sh staging.
4. After build succeeds, Apps > ZenCore Salesperson Tracking > Upgrade.
5. Log out and back in or hard refresh (Ctrl+Shift+R) to load fresh frontend assets.

## Test
1. CEO login, open the Salesperson Tracking app icon; Dashboard appears.
2. Manager login; Dashboard appears.
3. Supervisor login; Dashboard appears.
4. Salesperson login; My Visit Plans appears; Dashboard menu remains hidden.
5. As Manager, use Live Map search to focus a salesperson and check date filtering, reports, and menus.
6. Verify no `Service user is not available` in browser developer console.

## Validation limits
All Python files parsed; all XML files parsed; role entry JS passed `node --check`; ZIP integrity passed. Actual Odoo.sh registry upgrade, asset loading and role tests have not been executed here.
