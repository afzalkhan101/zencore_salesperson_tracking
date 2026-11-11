# V20.11 Odoo 19 report model name fix

## Root cause
The abstract QWeb report models for Customer Detailed and Salesperson Performance had implicit table identifiers longer than 63 characters. Odoo model setup rejects those names even for abstract reports.

## Changes
- Customer Detailed QWeb model now explicitly sets `_table = "zc_customer_report_render"`.
- Salesperson Performance QWeb model now explicitly sets `_table = "zc_performance_report_render"`.
- `_name`, XML report IDs, report actions, templates and report permissions are unchanged.
- Module version: 19.0.11.0.11.

## Staging deployment
1. Take an Odoo.sh staging backup.
2. Update existing `zencore_salesperson_tracking` folder; do not install a second addon.
3. Push branch and upgrade ZenCore Salesperson Tracking.
4. Test Customer Detailed and Performance PDFs as CEO/Manager/Supervisor, verify salesperson denial and cross-team isolation.

## Verification scope
Python syntax, XML well-formedness, names and zip integrity were checked. Odoo registry initialization and live print tests require staging.
