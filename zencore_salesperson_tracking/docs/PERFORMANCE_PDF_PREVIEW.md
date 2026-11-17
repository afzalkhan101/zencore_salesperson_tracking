# Salesperson Performance PDF Preview (Odoo 19)

Version: 19.0.11.0.88

Replace the existing salesperson tracking addon with the updated directory. Back up the database first. Upgrade `zencore_salesperson_tracking` and restart Odoo. Refresh browser assets with Ctrl+Shift+R.

## Verification

1. Log in as an authorized CEO, Manager or Supervisor.
2. Open Salesperson Tracking > Reports > Salesperson Performance Report. Set filters. The form only displays filters and actions, not the performance snapshot or detail tables.
3. Click Generate report. A full-screen Odoo dialog should show the actual multipage QWeb PDF, not an HTML approximation.
4. Use the PDF viewer navigation, zoom, sidebar thumbnails and print control. Verify the printed page count, content and orientation match the preview. Printer settings can affect physical margins and scaling.
5. Download PDF using the dialog button and verify it has the same contents. Use a local PDF reader if browser printing is unavailable. Close the dialog and confirm the existing filters remain.
6. In browser developer tools, confirm one request to `/report/pdf/zencore_salesperson_tracking.report_salesperson_performance_document/<wizard-id>` per preview; print and download should not request report regeneration.
7. Try with an unauthorized user or another user's wizard ID: the existing secure report renderer must reject access.
8. Verify Excel export works directly from the filters, even before opening a PDF; the export controller regenerates results from the current saved filters. Verify visit calculations still work. Check behavior with a large report, missing PDF renderer, and closing during loading.

The redesigned QWeb template uses teal KPI cards, horizontal status and comparison charts, and dedicated completed and missed registers. The existing paper format, report security, Excel export and visit calculations are unchanged. The viewer uses Odoo's bundled PDF.js and an in-memory PDF object URL, released when the dialog closes. No new database storage or external viewer service is used. Live browser and Odoo installation tests are required in staging.
