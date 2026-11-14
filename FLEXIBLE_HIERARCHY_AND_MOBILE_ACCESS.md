# Flexible reporting hierarchy and mobile salesperson access

## What changes

- `Reports To` on **Users** is optional. A single user has one direct manager;
  one manager can have multiple direct reports.
- The server enforces the permitted relationships: Manager → CEO, Supervisor →
  CEO/Manager, Salesperson → CEO/Manager/Supervisor. CEO has no superior.
- Self references, circular paths, inactive managers and cross-company
  assignments are rejected on the server. An active report must be reassigned
  before its manager can be archived.
- CEOs monitor all internal users in their active company. Managers and
  supervisors retain monitoring only for their own reporting subtree. This is
  consumed by the existing visit-plan, GPS, map, dashboard and report record
  rules; a reporting line does not add Odoo groups or administrator rights.
- **Reports → Reporting Hierarchy** provides the native Odoo hierarchy and a
  list view of the real relationships. The old Organization menu remains
  hidden as requested.

## Mobile self-registration

When the configuration parameter
`zencore_field_mobile_bridge.registration_enabled` is enabled, the mobile app
creates an active internal user with exactly these baseline permissions:

- `base.group_user`
- `zencore_salesperson_tracking.group_salesperson_salesman`

The role/group synchronization in the tracking module keeps this user as a
Salesperson. It does **not** add CEO, Manager, Supervisor, System
Administrator, or sales-management groups. Existing ACLs and record rules
therefore allow only the new user's operational records while preserving the
mobile application's visit plans, GPS, check-in/out, photo evidence,
customers, profile and offline-sync endpoints.

Public signup never accepts a company, a reporting-manager id, or a role other
than `salesman`. The reporting line starts empty and can later be assigned by
an authorized CEO/Manager. Password validation, normalized-login duplicate
checks, a transactional PostgreSQL advisory lock, generic duplicate responses,
and the existing per-IP rate limit remain enabled.

## Odoo installation / upgrade

1. Deploy both modules from the repository root:

   ```bash
   /home/betopi/odoo/launch.sh 19 -d YOUR_DATABASE \
     -u zencore_salesperson_tracking,zencore_field_mobile_bridge
   ```

2. In Odoo, enable self-registration only if this is an intended public flow:
   **Settings → Technical → System Parameters** → set
   `zencore_field_mobile_bridge.registration_enabled` to `True`.
3. Configure a company CEO manual approver when manual approval needs a fixed
   fallback. If no reporting manager and no unique/configured CEO exists, a
   plan can still be submitted but is deliberately left without an approver;
   this avoids inventing privilege or silently auto-approving it.
4. In the Expo app, open **Profile**. It shows the server-authoritative Role
   and Reports To name (or `Not assigned`).

## Test checklist

- Create a CEO; then test Manager → CEO, Supervisor → CEO and → Manager, and
  Salesperson → CEO/Manager/Supervisor. Test a Salesperson with no Reports To.
- Confirm self-reporting, a cycle, an inactive manager and a second-company
  manager all fail with a validation error.
- Sign up with the mobile app, then immediately sign in. Confirm the user has
  the Salesperson group only and can create/submit their own visit plan, use
  tracking/check-in/photos/customers and view their own profile.
- Verify that the new user cannot open another salesperson's records or use
  CEO/Manager/Supervisor/Settings features.
- Confirm a CEO sees unassigned salespeople and their historical GPS/visit
  data; confirm a manager/supervisor sees only their reporting subtree.

## Rollback

Roll back by deploying the preceding Git commit and updating the two modules.
No data migration deletes users, reporting lines, visits, GPS points or photo
evidence. Before rolling back a code version, resolve any hierarchy values
that older strict versions cannot accept (for example Salesperson → CEO).
