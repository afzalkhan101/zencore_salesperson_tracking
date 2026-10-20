import io

from odoo import http
from odoo.http import request

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None


class SalespersonPerformanceReportExportController(http.Controller):

    @http.route('/salesperson/performance_report/xlsx/<int:wizard_id>', type='http', auth='user')
    def export_xlsx(self, wizard_id, **kwargs):
        manager_group = request.env.ref('zencore_salesperson_tracking.group_salesperson_manager', raise_if_not_found=False)
        if not manager_group or manager_group not in request.env.user.group_ids:
            return request.not_found()

        wizard = request.env['salesperson.performance.report.wizard'].sudo().browse(wizard_id).exists()
        if not wizard:
            return request.not_found()
        if not wizard.line_ids:
            wizard.action_generate_report()

        if xlsxwriter is None:
            return request.make_response(
                'Excel export requires the Python package xlsxwriter.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=500,
            )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#1F3B6D'})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': 'white', 'border': 1})
        subheader_fmt = workbook.add_format({'bold': True, 'bg_color': '#EDE9FE', 'border': 1})
        cell_fmt = workbook.add_format({'border': 1})
        number_fmt = workbook.add_format({'border': 1, 'num_format': '0.00'})
        percent_fmt = workbook.add_format({'border': 1, 'num_format': '0.0"%"'})
        date_fmt = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})
        datetime_fmt = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm'})

        # Summary sheet
        sheet = workbook.add_worksheet('Summary')
        sheet.set_column('A:A', 26)
        sheet.set_column('B:B', 18)
        sheet.write('A1', 'Salesperson Performance Report', title_fmt)
        sheet.write('A3', 'Report Type', subheader_fmt)
        sheet.write('B3', dict(wizard._fields['report_type'].selection).get(wizard.report_type), cell_fmt)
        sheet.write('A4', 'From Date', subheader_fmt)
        sheet.write('B4', str(wizard.date_from or ''), cell_fmt)
        sheet.write('A5', 'To Date', subheader_fmt)
        sheet.write('B5', str(wizard.date_to or ''), cell_fmt)
        metrics = [
            ('Total Salespersons', wizard.total_salespersons),
            ('Planned Visits', wizard.total_planned_visits),
            ('Completed Visits', wizard.total_completed_visits),
            ('Pending Visits', wizard.total_pending_visits),
            ('Completion %', wizard.completion_percent),
            ('Total Distance (KM)', wizard.total_distance_km),
            ('Tracking Time (Min)', wizard.total_tracking_minutes),
            ('Visit Time (Min)', wizard.total_visit_minutes),
            ('Idle Time (Min)', wizard.total_idle_minutes),
            ('Total Expense', wizard.total_expense),
            ('Average Rating', wizard.average_rating),
        ]
        row = 7
        for label, value in metrics:
            sheet.write(row, 0, label, subheader_fmt)
            sheet.write(row, 1, value, number_fmt if isinstance(value, float) else cell_fmt)
            row += 1

        # Salesperson summary sheet
        sheet = workbook.add_worksheet('Salespersons')
        headers = ['Salesperson', 'Planned', 'Completed', 'Pending', 'Completion %', 'Distance KM',
                   'Tracking Min', 'Visit Min', 'Idle Min', 'Expense', 'Avg Rating']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_fmt)
        sheet.set_column(0, 0, 28)
        sheet.set_column(1, 10, 14)
        for row, line in enumerate(wizard.line_ids, start=1):
            values = [line.user_id.name, line.planned_visits, line.completed_visits, line.pending_visits,
                      line.completion_percent, line.distance_km, line.tracking_minutes, line.visit_minutes,
                      line.idle_minutes, line.expense, line.average_rating]
            for col, value in enumerate(values):
                fmt = percent_fmt if col == 4 else (number_fmt if col >= 5 else cell_fmt)
                sheet.write(row, col, value, fmt)

        # Day-wise summary
        sheet = workbook.add_worksheet('Day Wise')
        headers = ['Date', 'Planned', 'Completed', 'Pending', 'Distance KM', 'Visit Min', 'Idle Min']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_fmt)
        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 6, 14)
        for row, line in enumerate(wizard.day_line_ids, start=1):
            sheet.write_datetime(row, 0, line.date, date_fmt) if line.date else sheet.write(row, 0, '', cell_fmt)
            for col, value in enumerate([line.planned_visits, line.completed_visits, line.pending_visits,
                                         line.distance_km, line.visit_minutes, line.idle_minutes], start=1):
                sheet.write(row, col, value, number_fmt if col >= 4 else cell_fmt)

        # Visit details
        sheet = workbook.add_worksheet('Visit Details')
        headers = ['Date', 'Salesperson', 'Customer', 'Purpose', 'Check In', 'Check Out', 'Duration Min',
                   'Tracker Distance KM', 'Status', 'Outcome', 'Rating']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_fmt)
        sheet.set_column(0, 0, 14)
        sheet.set_column(1, 3, 24)
        sheet.set_column(4, 5, 20)
        sheet.set_column(6, 10, 16)
        for row, line in enumerate(wizard.visit_line_ids, start=1):
            if line.visit_date:
                sheet.write_datetime(row, 0, line.visit_date, date_fmt)
            sheet.write(row, 1, line.user_id.name or '', cell_fmt)
            sheet.write(row, 2, line.partner_id.name or '', cell_fmt)
            purpose = dict(line._fields['purpose'].selection).get(line.purpose, '') if line.purpose else ''
            sheet.write(row, 3, purpose, cell_fmt)
            if line.checkin_time:
                sheet.write_datetime(row, 4, line.checkin_time, datetime_fmt)
            if line.checkout_time:
                sheet.write_datetime(row, 5, line.checkout_time, datetime_fmt)
            sheet.write(row, 6, line.duration_minutes, number_fmt)
            sheet.write(row, 7, line.distance_km, number_fmt)
            status = dict(line._fields['status'].selection).get(line.status, '') if line.status else ''
            outcome = dict(line._fields['outcome'].selection).get(line.outcome, '') if line.outcome else ''
            sheet.write(row, 8, status, cell_fmt)
            sheet.write(row, 9, outcome, cell_fmt)
            sheet.write(row, 10, line.rating, number_fmt)

        workbook.close()
        output.seek(0)
        filename = 'Salesperson_Performance_%s_%s.xlsx' % (wizard.date_from, wizard.date_to)
        return request.make_response(
            output.read(),
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', 'attachment; filename="%s"' % filename),
            ],
        )
