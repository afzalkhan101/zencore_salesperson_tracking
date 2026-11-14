# ZenCore Field V8 — Odoo Visit Plan Parity

## What changed

The Visit Plan editor is now a four-step flow that corresponds to the existing Odoo 19 `salesperson.visit.plan` and `salesperson.visit.plan.line` fields:

1. **Basic Info** — salesperson (assigned from authenticated account), Visit Date, Purpose, Priority, Total Visits (derived from customers).
2. **Target Lines** — multi-select Odoo Customers, Expected Time (minutes), multi-select accompanying Employees, From Location, To Location, Expected KM (manual), and line Notes. Multiple lines can be added, edited, or removed.
3. **Expenses & Notes** — Transport, Food, Other and automatically calculated Total, plus Plan Notes.
4. **Review** — checks all entered lines, saves a local draft or creates the Odoo Visit Plan directly in `Submitted` state.

Odoo generates the actual plan reference, computes `total_visits` and `total_cost`, and retains existing manager approval, tracking, and reporting methods. After the manager approves a submitted plan, use **Visits → Refresh Odoo Plans** to see `Approved`, then begin plan-specific GPS tracking.

## Odoo field mapping

| Mobile | Odoo model/field |
|---|---|
| Salesperson | `salesperson.visit.plan.user_id` — server sets authenticated Odoo user |
| Date | `visit_date` |
| Purpose | `purpose` (`followup`, `order`, `payment`, `complaint`, `demo`) |
| Priority | `priority` (`0` Normal, `1` High, `2` Urgent) |
| Transport | `transport_cost` |
| Food | `food_cost` |
| Other | `other_cost` |
| Total Expenses | `total_cost` — Odoo computed |
| Plan Notes | `internal_notes` |
| Time (min) | `target_line_ids.expected_time_minutes` |
| Accompanies | `target_line_ids.employee_ids` (M2M) |
| From Location | `target_line_ids.from_location` |
| To Location | `target_line_ids.to_location` |
| KM | `target_line_ids.expected_km` |
| Customers | `target_line_ids.customer_ids` (M2M) |
| Line Notes | `target_line_ids.notes` |
| Total Visits | `total_visits` — Odoo computed from customer counts |
| Approval status | `state` — submitted by mobile, manager approves in existing Odoo form |

**Important:** Expected KM is manually entered; this version does NOT claim automatic road routing. Company-specific constraints and API permissions require staging tests. `employee_ids` candidates are scoped to the authenticated user's active company.

## Install backend FIRST (Odoo.sh staging)

1. Extract `ZenCoreField_V8_VisitPlan_Parity.zip`.
2. Copy `ZenCoreFieldFull/odoo_addon/zencore_field_mobile_bridge` into the Odoo.sh repository's custom addons path. Keep the existing `zencore_salesperson_tracking` addon installed.
3. Commit and push to the **staging** branch; wait for successful deployment.
4. Odoo → Apps → Update Apps List → **ZenCore Field Mobile Bridge** → Upgrade (new manifest version `19.0.5.0.0`).
5. Ensure the existing Visit Plan form and Manager Approval still operate normally.
6. While signed into staging, test `/zencore/field/v3/health` (should return JSON). `GET /zencore/field/v4/employees` and `GET /zencore/field/v4/plans/<ID>` require an authenticated session. If the route is missing/404, confirm the addon was installed on the exact database/branch used by the phone.

## Run on Ubuntu (NEW source folder)

```bash
node -v                # Node 22+
java -version          # JDK 17
adb devices -l         # Android phone should say 'device'
mkdir -p ~/ZenCoreFieldV8
unzip ~/Downloads/ZenCoreField_V8_VisitPlan_Parity.zip -d ~/ZenCoreFieldV8
cd ~/ZenCoreFieldV8/ZenCoreFieldFull
npm install
npx expo install --check
npx tsc --noEmit
npx expo config --type public
npx expo prebuild --platform android --clean
npx expo run:android --device
```

`prebuild --clean` overwrites existing generated native files; use only a fresh extraction or back up `android/` first. The full native build was not possible to run in the packaging environment.

If Metro is not running after build:

```bash
adb reverse tcp:8081 tcp:8081
npx expo start --dev-client --clear
```

Open the installed **ZenCore Field development app**, not Expo Go. Edit only the new `~/ZenCoreFieldV8/ZenCoreFieldFull` folder, and don't run Metro from an older V6/V7 folder.

## End-to-end staging test

1. Profile → Odoo URL, database name, username, password → Login.
2. Visits → New Plan → Basic Info (today/future date, purpose, priority).
3. Target Lines → Select Customers → choose **two** customers → Done; select an accompanying employee; enter minutes, from, to, expected KM and notes → Add Target Line.
4. Add a second target line, including a customer. Verify count and edit one line.
5. Expenses → Transport 250, Food 100, Other 50; total should display **BDT 400.00**. Enter Plan Notes.
6. Review → Submit to Odoo. Confirm server-generated plan name and Submitted state.
7. In Odoo: Visit Plans → open that same plan. Check salesperson, date, purpose, priority, Expenses Claim, Total Visits, both target lines, all customer tags, employee tags, minutes, from/to, KM and notes. Approve using the existing Odoo button.
8. Mobile: Visits → Refresh Odoo Plans → the same plan should become Approved. Open to see the server detail values and plan-wise Start Tracking.
9. Tracking: verify active plan ID; sync points; check server accepted/rejected counts and Location Data. GPS remains a device/OS-specific, separately tested capability.

## Troubleshooting

- **HTTP 404 `/zencore/field/v4/employees`** — bridge not updated on the same Odoo.sh branch/database.
- **Odoo HTTP 400** — inspect the displayed JSON `message`; confirm customer IDs, employee IDs, required locations, date, and amounts.
- **No employees** — no employees are assigned to the logged-in user's active company, or HR is not installed.
- **Approval not refreshed** — tap Refresh Odoo Plans, and ensure manager approved the same Plan ID.
- **Same old app** — kill older Metro servers, verify `pwd`, reload the newly built development app.
- **Road KM** — manual entry by design. No routing service is configured.
- **Odoo server update** — upgrading only Android does not install server APIs.

## Status and constraints

Source-level TypeScript transpilation and Python compilation were checked, as were the route and field mappings. The full `npm install`, `tsc --noEmit`, Android/iOS build, Odoo.sh deployment, and real GPS tests remain for your environment. Preserve staging backup before deploying. This update does not override Odoo manager approvals or directly change the original Salesperson Tracking module.
