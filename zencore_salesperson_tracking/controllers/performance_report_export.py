import io

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError
from ..models.report_security import check_report_access
from ..models.report_render_security import _visible_documents

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None


class SalespersonPerformanceReportExportController(http.Controller):

    @http.route('/salesperson/performance_report/xlsx/<int:wizard_id>', type='http', auth='user')
    def export_xlsx(self, wizard_id, **kwargs):
        try:
            check_report_access(request.env)
        except AccessError:
            return request.not_found()

        wizard = request.env['salesperson.performance.report.wizard'].browse(wizard_id).exists()
        # Never export someone else's transient wizard, even with a guessed ID.
        if wizard and wizard.create_uid != request.env.user:
            return request.not_found()
        if not wizard:
            return request.not_found()
        try:
            _visible_documents(request.env, wizard._name, [wizard.id], wizard=True)
            wizard.action_generate_report()
        except AccessError:
            return request.not_found()

        if xlsxwriter is None:
            return request.make_response(
                'Excel export requires the Python package xlsxwriter.',
                headers=[('Content-Type', 'text/plain; charset=utf-8')],
                status=500,
            )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'font_color': '#1F3B6D'})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': 'white', 'border': 1})
        subheader_fmt = workbook.add_format({'bold': True, 'bg_color': '#EDE9FE', 'border': 1})
        cell_fmt = workbook.add_format({'border': 1})
        number_fmt = workbook.add_format({'border': 1, 'num_format': '0.00'})
        percent_fmt = workbook.add_format({'border': 1, 'num_format': '0.0"%"'})
        date_fmt = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd'})
        datetime_fmt = workbook.add_format({'border': 1, 'num_format': 'yyyy-mm-dd hh:mm'})

        def label(record, field):
            return dict(record._fields[field]._description_selection(request.env)).get(record[field], '')

        def local_datetime(value):
            return fields.Datetime.context_timestamp(wizard, value).replace(tzinfo=None) if value else ''

        def make_sheet(name, headers, rows):
            sheet = workbook.add_worksheet(name)
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, len(headers)-1, 20)
            for col, header in enumerate(headers):
                sheet.write(0, col, header, header_fmt)
            status_formats = {"Missed": workbook.add_format({'border': 1, 'font_color': '#B42318'}), "Overdue": workbook.add_format({'border': 1, 'font_color': '#B42318'}), "Completed": workbook.add_format({'border': 1, 'font_color': '#087F5B'})}
            for rownum, row in enumerate(rows, 1):
                for col, value in enumerate(row):
                    fmt = number_fmt if isinstance(value, float) else cell_fmt
                    if headers[col] == 'Status':
                        fmt = status_formats.get(value, cell_fmt)
                    if headers[col] in ('Check-in', 'Check-out') and value:
                        sheet.write_datetime(rownum, col, value, datetime_fmt)
                    else:
                        sheet.write(rownum, col, value if value is not None else '', fmt)
            sheet.autofilter(0, 0, len(rows), len(headers)-1)
            return sheet

        keys = ('planned', 'completed', 'missed', 'pending', 'in_progress', 'overdue', 'awaiting_approval', 'rejected', 'unplanned')
        metrics = [('From date', str(wizard.date_from)), ('To date', str(wizard.date_to)), ('Detail status', label(wizard, 'visit_status')), ('Salespeople', wizard.total_salespersons), ('Customers', wizard.total_customers), ('Visited customers', wizard.total_visited_customers)]
        metrics += [(key.replace('_', ' ').title(), wizard['total_' + key + '_visits']) for key in keys]
        metrics += [('Completion %', wizard.completion_percent), ('Distance km', wizard.total_distance_km), ('Tracking min', wizard.total_tracking_minutes), ('Visit min', wizard.total_visit_minutes), ('Idle min', wizard.total_idle_minutes), ('Estimated expense', wizard.total_estimated_expense), ('Actual expense', wizard.total_expense), ('Average rating', wizard.average_rating), ('Definition', 'Missed: scheduled date elapsed without check-in; unapproved/rejected excluded from completion rate.'), ('Scope', 'Status filter applies to detail sheets only. Completed summary counts planned visits; distance and actual expense are tracker totals; estimated expense is plan/tracker level.')]
        make_sheet('Summary', ['Metric', 'Value'], metrics).set_column(1, 1, 85)
        count_headers = ['Completed planned' if k == 'completed' else k.replace('_', ' ').title() for k in keys]
        make_sheet('Salespersons', ['Salesperson', 'Customers', 'Visited customers'] + count_headers + ['Completion %', 'Distance km', 'Tracking min', 'Visit min', 'Idle min', 'Estimated expense', 'Actual expense', 'Rating'], [[l.user_id.name, l.customer_count, l.visited_customer_count] + [l[k + '_visits'] for k in keys] + [l.completion_percent, l.distance_km, l.tracking_minutes, l.visit_minutes, l.idle_minutes, l.estimated_expense, l.expense, l.average_rating] for l in wizard.line_ids])
        make_sheet('Day Wise', ['Date'] + count_headers + ['Distance km', 'Visit min', 'Idle min'], [[str(l.date)] + [l[k + '_visits'] for k in keys] + [l.distance_km, l.visit_minutes, l.idle_minutes] for l in wizard.day_line_ids])
        headers = ['Reference', 'Date', 'Salesperson', 'Customer', 'Planned', 'Purpose', 'Status', 'Check-in', 'Check-out', 'Minutes', 'Outcome', 'Rating', 'Status Explanation', 'Notes', 'Feedback', 'Photo Evidence', 'Tracker Distance km (not additive)', 'Check-in location', 'Latitude', 'Longitude']
        def visit_values(l):
            return [l.reference or '', str(l.visit_date), l.user_id.name, l.partner_id.name, 'Yes' if l.is_planned else 'No', label(l, 'purpose'), label(l, 'status'), local_datetime(l.checkin_time), local_datetime(l.checkout_time), l.duration_minutes, label(l, 'outcome'), l.rating, l.reason or '', l.notes or '', l.customer_feedback or '', 'Yes' if l.photo_available else 'No', l.distance_km, l.location_name or '', l.checkin_latitude if l.checkin_id else '', l.checkin_longitude if l.checkin_id else '']
        for title, records in [('Visit Details', wizard.visit_line_ids), ('Missed and Overdue', wizard.missed_line_ids), ('Completed Visits', wizard.completed_line_ids)]:
            sheet = make_sheet(title, headers, [visit_values(l) for l in records])
            sheet.set_column(12, 14, 42)
        groups = {}
        for l in wizard.visit_line_ids:
            groups.setdefault((l.user_id.id, l.partner_id.id), []).append(l)
        customers = []
        for rows in groups.values():
            completed = [l for l in rows if l.status == 'completed']
            last = max((l.visit_date for l in completed if l.visit_date), default=False)
            customers.append([rows[0].user_id.name, rows[0].partner_id.name, sum(l.is_planned for l in rows), len(completed), sum(l.status in ('missed', 'overdue') for l in rows), sum(l.status == 'pending' for l in rows), sum(not l.is_planned for l in rows), str(last or '')])
        make_sheet('Customer Analysis', ['Salesperson', 'Customer', 'Planned', 'Completed (all)', 'Missed or overdue', 'Pending', 'Unplanned', 'Last completed in period'], customers)
        make_sheet('Travel and Expenses', ['Salesperson', 'Distance km', 'Tracking min', 'Visit min', 'Idle min', 'Estimated expense', 'Actual expense', 'Rating'], [[l.user_id.name, l.distance_km,l.tracking_minutes,l.visit_minutes,l.idle_minutes,l.estimated_expense,l.expense,l.average_rating] for l in wizard.line_ids])

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
