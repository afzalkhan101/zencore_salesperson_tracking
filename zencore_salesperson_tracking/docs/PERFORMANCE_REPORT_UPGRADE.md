# Salesperson Performance Report — Odoo 19

Release: 19.0.11.0.85

## Upgrade

1. Take a database and filestore backup. Use a staging database first.
2. Replace the `zencore_salesperson_tracking` addon directory with this release. Do not overwrite other custom addons. The bundled `zencore_field_mobile_bridge` is unchanged.
3. Restart Odoo and upgrade the module in Apps, or stop Odoo and run:

   ```bash
   ./odoo-bin -c /path/to/odoo.conf -d YOUR_DATABASE -u zencore_salesperson_tracking --stop-after-init
   ```

4. Restart the Odoo service. Hard refresh the browser (Ctrl+Shift+R).
5. Log in as a CEO, Manager or Supervisor. Open Salesperson Tracking > Reports > Performance Report. Choose dates and optional scope, then Generate report. Use All status for a complete register.
6. Open Print PDF and Export Excel. Excel requires xlsxwriter. PDF requires the deployment's supported wkhtmltopdf setup.

## Report rules

- One planned visit row per customer on each target line. A check-in can satisfy only one planned row. Exact target-line matches take priority; historic check-ins without a target line may match by plan and customer. Additional check-ins are identified as unplanned/repeat check-ins, not counted toward planned completion.
- Completed: matched check-in has checked-out state. In progress: checked-in on current/future visit date. Overdue: an earlier-date visit has check-in but no check-out. Missed: approved/in-progress/completed plan date is earlier than the user's timezone-local current date and no matching check-in exists. Today's unstarted visits remain pending until the date ends.
- Draft/submitted plans are awaiting approval and rejected plans are separate. Neither counts toward the completion-rate denominator. Planned total includes these visible target records. Unplanned visits do not affect planned completion rate. Customer coverage counts unique customers in the selected scope, including unplanned visits.
- The existing plan model records a scheduled DATE only, not a per-customer appointment time. It has no cancelled/rescheduled state or historical rescheduling log. The report does not invent these statuses or a planned time, delay, actual missed reason or future follow-up date. Notes and meeting outcome are actual recorded fields; status explanation is a derived rule, not a salesperson-provided excuse.
- The visit status selector filters the detail register and detail-derived tabs, not the KPI, salesperson, daily or travel totals. Customer filter includes only that customer's visit target rows, but tracking distance, estimated expenses and actual expenses are plan/session-level totals, not attributed customer costs. Distances displayed in individual visits can repeat the session's distance; do not sum these rows. Unique customer coverage is limited to the reporting period, not a lifetime list of assigned customers.
- GPS coordinates and photo availability reflect recorded check-in data; they do not imply an independent GPS verification. Open visit detail/source records to view available evidence. Odoo access rules continue to apply.
- The report changes only transient reporting data. It does not write statuses to visit plans, tracking sessions, GPS logs, or mobile APIs.

## UAT checklist

Use approved plans with at least two different customers. To create historical records, enter test plans on a staging database with appropriate test dates or use pre-existing historical demo records; production plan creation intentionally rejects past dates.

| Test | Expected outcome |
| --- | --- |
| Past approved plan, two customers, only one checked out | One Completed, one Missed; both named in Visit Details; 50% completion |
| Today's approved unstarted target | Pending, never Missed during today |
| Past check-in without checkout | Overdue; not Completed or Missed |
| Today's check-in without checkout | In progress |
| Past draft/submitted plan | Awaiting approval |
| Rejected plan | Rejected; excluded from completion denominator |
| Same customer appears on two target lines, one check-in | Only one planned target completed |
| Additional/unplanned check-in | Separate row marked Planned = No; completion rate cannot exceed 100% |
| Customer filter | Only selected customer appears in detail/target counts |
| Status = Missed | Detail contains missed records only; summary stays at selected scope |
| Manager/Supervisor outside report hierarchy | Cannot generate reports for unauthorized users |
| Open a visit row | Read-only details with source records, notes, outcome, check-in data and available photo |
| Export PDF | Management totals, daily summary, customer-wise register, missed/overdue list, customer coverage, travel/expense section; company layout and A4 landscape |
| Export Excel | Eight sheets: Summary, Salespersons, Day Wise, Visit Details, Missed and Overdue, Completed Visits, Customer Analysis, Travel and Expenses |

## Validation performed before delivery

- Python source parsed and compiled, XML files parsed, manifest paths checked, ZIP content verified.
- `python docs/test_performance_report_logic.py`: standalone isolated test runs the actual report reconciliation and counting methods using mock records. Covers missed, pending, overdue, completed, in-progress, unapproved, rejected, repeated targets, unplanned visits and customer filter.
- No Odoo server/database in the development environment. Odoo ORM installation, access-rule integration, client-side rendering and wkhtmltopdf output still require staging UAT. The final UI uses native Odoo form/list views and charts built from report data rather than a pixel-identical mockup; no unsupported appointment timings or cancellation states are fabricated.
