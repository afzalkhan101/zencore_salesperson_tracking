import io

from odoo import fields, http
from odoo.exceptions import AccessError
from odoo.http import request

from ..models.report_render_security import _visible_documents
from ..models.report_security import check_report_access

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None


class SalespersonCustomerReportExportController(http.Controller):
    """Export the customer report using the same ownership and role checks as PDF."""

    @http.route('/salesperson/customer_report/xlsx/<int:wizard_id>', type='http', auth='user')
    def export_xlsx(self, wizard_id, **kwargs):
        try:
            check_report_access(request.env)
            wizard = request.env['salesperson.customer.report.wizard'].browse(wizard_id).exists()
            if not wizard or wizard.create_uid != request.env.user:
                return request.not_found()
            _visible_documents(request.env, wizard._name, [wizard.id], wizard=True)
            wizard.action_generate_report()
        except AccessError:
            return request.not_found()

        if xlsxwriter is None:
            return request.make_response(
                'Excel export requires the Python package xlsxwriter.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')], status=500,
            )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {
            'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False,
        })
        header = workbook.add_format({'bold': True, 'bg_color': '#EDEDED', 'border': 1})
        cell = workbook.add_format({'border': 1})
        number = workbook.add_format({'border': 1, 'num_format': '0.00'})
        percent = workbook.add_format({'border': 1, 'num_format': '0.0"%"'})
        date_format = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})
        datetime_format = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm'})

        def duration(minutes):
            total = int(minutes or 0)
            return '%d h %d min' % (total // 60, total % 60)

        def local_datetime(value):
            return fields.Datetime.context_timestamp(wizard, value).replace(tzinfo=None) if value else ''

        def sheet(name, headers, rows, date_columns=(), datetime_columns=(), percent_columns=()):
            worksheet = workbook.add_worksheet(name)
            worksheet.freeze_panes(1, 0)
            worksheet.set_column(0, len(headers) - 1, 18)
            for column, label in enumerate(headers):
                worksheet.write(0, column, label, header)
            for row_no, values in enumerate(rows, 1):
                for column, value in enumerate(values):
                    if column in date_columns and value:
                        worksheet.write_datetime(row_no, column, value, date_format)
                    elif column in datetime_columns and value:
                        worksheet.write_datetime(row_no, column, value, datetime_format)
                    else:
                        fmt = percent if column in percent_columns else number if isinstance(value, float) else cell
                        worksheet.write(row_no, column, value if value is not None else '', fmt)
            worksheet.autofilter(0, 0, max(1, len(rows)), len(headers) - 1)
            return worksheet

        scope_users = wizard.individual_user_id.name if wizard.report_type == 'individual' else (', '.join(wizard.user_ids.mapped('name')) if wizard.salesperson_scope == 'selected' else 'All permitted salespersons')
        metrics = [
            ('From date', str(wizard.date_from)), ('To date', str(wizard.date_to)),
            ('Salespersons', scope_users), ('Customer', wizard.partner_id.name if wizard.customer_scope == 'selected' else 'All customers'),
            ('Visit status', wizard.visit_status), ('Customers', wizard.total_customers),
            ('Planned visits', wizard.total_visits), ('Completed visits', wizard.completed_visits),
            ('Remaining visits', wizard.pending_visits + wizard.in_progress_visits), ('Missed / overdue', wizard.missed_visits),
            ('Completion %', wizard.completion_percent), ('Distance km', wizard.total_distance_km),
            ('Tracking time', duration(wizard.total_tracking_minutes)), ('Visit time', duration(wizard.total_visit_minutes)),
            ('Idle time', duration(wizard.total_idle_minutes)), ('Actual expense', wizard.total_expense),
        ]
        sheet('Summary', ['Metric', 'Value'], metrics).set_column(1, 1, 42)
        sheet('Customers', ['Customer', 'Salespeople', 'Planned', 'Completed', 'Remaining', 'Missed', 'Completion %', 'Distance km', 'Visit time', 'Last completed visit'], [
            [line.partner_id.name, line.salesperson_count, line.planned, line.completed, line.pending + line.in_progress, line.missed, line.completion_percent, line.distance_km, duration(line.visit_minutes), line.last_visit_date] for line in wizard.customer_line_ids
        ], date_columns=(9,), percent_columns=(6,))
        sheet('Daily Summary', ['Date', 'Planned', 'Completed', 'Remaining', 'Missed', 'Completion %', 'Distance km', 'Visit time'], [
            [line.date, line.planned, line.completed, line.pending + line.in_progress, line.missed, line.completion_percent, line.distance_km, duration(line.visit_minutes)] for line in wizard.day_line_ids
        ], date_columns=(0,), percent_columns=(5,))
        detail_headers = ['Reference', 'Date', 'Salesperson', 'Customer', 'Planned', 'Purpose', 'Status', 'Check-in', 'Check-out', 'Duration', 'Distance km', 'Outcome', 'Rating', 'Notes / reason']
        detail_rows = [[
            line.visit_plan_ref or '', line.visit_date, line.user_id.name, line.partner_id.name,
            'Yes' if line.is_planned else 'No', line.purpose or '', line.status or '',
            local_datetime(line.checkin_time), local_datetime(line.checkout_time), duration(line.duration_minutes),
            line.distance_km, line.outcome or '', line.rating, line.reason or line.notes or line.customer_feedback or '',
        ] for line in wizard.line_ids]
        details = sheet('Visit Details', detail_headers, detail_rows, date_columns=(1,), datetime_columns=(7, 8))
        details.set_column(13, 13, 46)

        workbook.close()
        output.seek(0)
        return request.make_response(output.read(), headers=[
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', 'attachment; filename="Customer_Visit_Report_%s_%s.xlsx"' % (wizard.date_from, wizard.date_to)),
        ])
