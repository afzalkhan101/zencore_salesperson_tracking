from calendar import monthrange
from datetime import timedelta
from collections import defaultdict
from markupsafe import escape

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, AccessError
from .report_security import check_report_access, report_team_user_ids, check_report_user


class SalespersonPerformanceReportWizard(models.TransientModel):
    _name = "salesperson.performance.report.wizard"
    _description = "Salesperson Performance Report"
    _rec_name = "name"

    # A proper record name keeps the Odoo breadcrumb human-readable while the
    # transient form is open (instead of showing ``NewId_...``).
    name = fields.Char(
        string="Report Name",
        required=True,
        readonly=True,
        default=lambda self: _("Salesperson Performance Report"),
    )

    report_type = fields.Selection([
        ("monthly", "Monthly Report"),
        ("weekly", "Weekly Report"),
        ("individual", "Individual Salesperson"),
        ("multiple", "Multiple Salespersons"),
    ], required=True, default="monthly", string="Report Type")

    month_date = fields.Date(string="Month", default=lambda self: fields.Date.context_today(self).replace(day=1))
    week_start = fields.Date(string="Week Start", default=lambda self: self._default_week_start())
    period_preset = fields.Selection([
        ("today", "Today"),
        ("this_week", "This Week"),
        ("last_week", "Last Week"),
        ("this_month", "This Month"),
        ("last_month", "Last Month"),
        ("custom", "Custom Range"),
    ], string="Period", default="this_month")
    date_from = fields.Date(string="From Date", required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string="To Date", required=True, default=fields.Date.context_today)

    individual_user_id = fields.Many2one(
        "res.users", string="Salesperson",
        domain="[('salesperson_role', '=', 'salesman')]",
    )
    user_ids = fields.Many2many(
        "res.users", "salesperson_performance_report_user_rel", "wizard_id", "user_id",
        string="Salespersons", domain="[('salesperson_role', '=', 'salesman')]",
    )
    salesperson_scope = fields.Selection([
        ("all", "All Salespersons"),
        ("selected", "Selected Salespersons"),
    ], string="Salespersons", required=True, default="all",
       help="Use all salespersons you are authorised to monitor, or choose specific salespersons.")
    sale_team_id = fields.Many2one("crm.team", string="Sales Team")
    customer_scope = fields.Selection([
        ("all", "All Customers"),
        ("selected", "Selected Customer"),
    ], string="Customer", required=True, default="all",
       help="Use all customers, or limit the report to one customer.")
    partner_id = fields.Many2one("res.partner", string="Customer")
    visit_status = fields.Selection([
        ("all", "All"),
        ("completed", "Completed"),
        ("pending", "Pending"),
        ("missed", "Missed"),
        ("in_progress", "In Progress"),
        ("overdue", "Overdue"),
        ("awaiting_approval", "Awaiting Approval"),
        ("rejected", "Rejected"),
    ], default="all", required=True, string="Visit Details Status")
    visit_purpose = fields.Selection([
        ("all", "All"),
        ("order", "New Order"),
        ("payment", "Payment Collection"),
        ("complaint", "Complaint Resolution"),
        ("followup", "Follow Up"),
        ("demo", "Product Demo"),
    ], default="all", required=True, string="Visit Purpose")
    tracking_status = fields.Selection([
        ("all", "All"),
        ("planned", "Planned"),
        ("live", "Live"),
        ("offline", "Offline"),
        ("completed", "Completed"),
    ], default="all", required=True, string="Tracking Status")

    line_ids = fields.One2many("salesperson.performance.report.line", "wizard_id", string="Salesperson Summary", readonly=True)
    day_line_ids = fields.One2many("salesperson.performance.report.day.line", "wizard_id", string="Day-wise Summary", readonly=True)
    visit_line_ids = fields.One2many("salesperson.performance.report.visit.line", "wizard_id", string="Visit Details", readonly=True)

    missed_line_ids = fields.One2many("salesperson.performance.report.visit.line", "wizard_id", compute="_compute_visit_subsets")
    completed_line_ids = fields.One2many("salesperson.performance.report.visit.line", "wizard_id", compute="_compute_visit_subsets")
    customer_analysis_html = fields.Html(compute="_compute_analysis_html", sanitize=True)
    comparison_html = fields.Html(compute="_compute_analysis_html", sanitize=True)
    status_distribution_html = fields.Html(compute="_compute_status_distribution", sanitize=True)
    total_customers = fields.Integer(readonly=True)
    total_visited_customers = fields.Integer(readonly=True)
    total_missed_visits = fields.Integer(readonly=True)
    total_in_progress_visits = fields.Integer(readonly=True)
    total_overdue_visits = fields.Integer(readonly=True)
    total_awaiting_approval_visits = fields.Integer(readonly=True)
    total_rejected_visits = fields.Integer(readonly=True)
    total_unplanned_visits = fields.Integer(readonly=True)
    total_salespersons = fields.Integer(readonly=True)
    total_planned_visits = fields.Integer(readonly=True)
    total_completed_visits = fields.Integer(string="Completed Planned Visits", readonly=True)
    total_pending_visits = fields.Integer(readonly=True)
    total_distance_km = fields.Float(readonly=True)
    total_tracking_minutes = fields.Float(readonly=True)
    total_visit_minutes = fields.Float(readonly=True)
    total_idle_minutes = fields.Float(readonly=True)
    total_expense = fields.Float(readonly=True)
    total_estimated_expense = fields.Float(readonly=True)
    average_rating = fields.Float(readonly=True)
    completion_percent = fields.Float(readonly=True)

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1)

    @api.model
    def _default_week_start(self):
        today = fields.Date.context_today(self)
        return today - timedelta(days=today.weekday())

    @api.onchange("report_type", "month_date", "week_start", "period_preset")
    def _onchange_period(self):
        today = fields.Date.context_today(self)
        if self.report_type == "monthly":
            base = self.month_date or today.replace(day=1)
            self.date_from = base.replace(day=1)
            self.date_to = base.replace(day=monthrange(base.year, base.month)[1])
        elif self.report_type == "weekly":
            start = self.week_start or (today - timedelta(days=today.weekday()))
            start = start - timedelta(days=start.weekday())
            self.week_start = start
            self.date_from = start
            self.date_to = start + timedelta(days=6)
        elif self.report_type in ("individual", "multiple"):
            preset = self.period_preset or "this_month"
            if preset == "today":
                self.date_from = self.date_to = today
            elif preset == "this_week":
                start = today - timedelta(days=today.weekday())
                self.date_from, self.date_to = start, start + timedelta(days=6)
            elif preset == "last_week":
                start = today - timedelta(days=today.weekday() + 7)
                self.date_from, self.date_to = start, start + timedelta(days=6)
            elif preset == "this_month":
                self.date_from = today.replace(day=1)
                self.date_to = today.replace(day=monthrange(today.year, today.month)[1])
            elif preset == "last_month":
                first_this = today.replace(day=1)
                prev_last = first_this - timedelta(days=1)
                self.date_from = prev_last.replace(day=1)
                self.date_to = prev_last

    @api.onchange("salesperson_scope")
    def _onchange_salesperson_scope(self):
        for wizard in self:
            if wizard.salesperson_scope == "all":
                wizard.user_ids = [(5, 0, 0)]

    @api.onchange("user_ids")
    def _onchange_user_ids(self):
        for wizard in self:
            if wizard.user_ids and wizard.report_type != "individual":
                wizard.salesperson_scope = "selected"

    @api.onchange("customer_scope")
    def _onchange_customer_scope(self):
        for wizard in self:
            if wizard.customer_scope == "all":
                wizard.partner_id = False

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        for wizard in self:
            if wizard.partner_id:
                wizard.customer_scope = "selected"

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("From Date cannot be after To Date."))

    def _selected_users(self):
        self.ensure_one()
        check_report_access(self.env)
        User = self.env["res.users"].sudo()
        if self.report_type == "individual":
            if not self.individual_user_id:
                raise ValidationError(_("Please select a salesperson for the Individual report."))
            users = self.individual_user_id
        elif self.report_type == "multiple" and self.salesperson_scope == "selected":
            if not self.user_ids:
                raise ValidationError(_("Please select at least one salesperson for the Multiple Salespersons report."))
            users = self.user_ids
        else:
            users = self.user_ids if self.salesperson_scope == "selected" and self.user_ids else User.search([
                ("id", "in", list(report_team_user_ids(self.env))),
                ("salesperson_role", "=", "salesman"),
                ("active", "=", True),
            ])
        if self.sale_team_id:
            users = users.filtered(lambda u: u.sale_team_id == self.sale_team_id)
        permitted = report_team_user_ids(self.env)
        if any(u.id not in permitted for u in users):
            raise AccessError(_("Selected users must belong to your reporting hierarchy."))
        return users

    def _tracker_domain_for_user(self, user):
        domain = [
            ("user_id", "=", user.id),
            ("visit_date", ">=", self.date_from),
            ("visit_date", "<=", self.date_to),
        ]
        if self.tracking_status != "all":
            domain.append(("state", "=", self.tracking_status))
        if self.visit_purpose != "all":
            domain.append(("purpose", "=", self.visit_purpose))
        if self.partner_id:
            domain += ["|", ("target_line_ids.customer_ids", "in", self.partner_id.id), ("visited_line_ids.partner_id", "=", self.partner_id.id)]
        return domain

    def _plan_domain_for_user(self, user):
        domain = [
            ("user_id", "=", user.id),
            ("visit_date", ">=", self.date_from),
            ("visit_date", "<=", self.date_to),
        ]
        if self.visit_purpose != "all":
            domain.append(("purpose", "=", self.visit_purpose))
        if self.partner_id:
            domain.append(("target_line_ids.customer_ids", "in", self.partner_id.id))
        return domain

    def _checkin_domain_for_user(self, user):
        domain = [
            ("user_id", "=", user.id),
            ("tracker_id.visit_date", ">=", self.date_from),
            ("tracker_id.visit_date", "<=", self.date_to),
        ]
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        if self.visit_purpose != "all":
            domain.append(("tracker_id.purpose", "=", self.visit_purpose))
        if self.tracking_status != "all":
            domain.append(("tracker_id.state", "=", self.tracking_status))
        return domain

    @api.depends("visit_line_ids.status")
    def _compute_visit_subsets(self):
        for wizard in self:
            wizard.missed_line_ids = wizard.visit_line_ids.filtered(lambda row: row.status in ("missed", "overdue"))
            wizard.completed_line_ids = wizard.visit_line_ids.filtered(lambda row: row.status == "completed")

    @api.depends("visit_line_ids.status", "visit_line_ids.is_planned", "visit_line_ids.user_id", "visit_line_ids.partner_id", "visit_line_ids.visit_date", "line_ids.completion_percent", "line_ids.planned_visits", "line_ids.completed_visits", "line_ids.missed_visits")
    def _compute_analysis_html(self):
        for wizard in self:
            buckets = defaultdict(list)
            for row in wizard.visit_line_ids:
                buckets[(row.user_id.id, row.partner_id.id)].append(row)
            head = '<table class="table table-sm table-bordered"><thead><tr><th>Salesperson</th><th>Customer</th><th>Planned</th><th>Completed</th><th>Missed / overdue</th><th>Pending</th><th>Unplanned</th><th>Last completed (period)</th></tr></thead><tbody>'
            body = []
            for rows in sorted(buckets.values(), key=lambda items: (items[0].user_id.name or "", items[0].partner_id.name or "")):
                user, customer = rows[0].user_id.name, rows[0].partner_id.name
                completed = [r for r in rows if r.status == "completed"]
                last = max((r.visit_date for r in completed if r.visit_date), default=False)
                values = [user, customer, sum(r.is_planned for r in rows), len(completed), sum(r.status in ("missed", "overdue") for r in rows), sum(r.status == "pending" for r in rows), sum(not r.is_planned for r in rows), last or "—"]
                body.append('<tr>' + ''.join('<td>%s</td>' % escape(v) for v in values) + '</tr>')
            wizard.customer_analysis_html = head + ''.join(body) + '</tbody></table>'
            rows = []
            for line in wizard.line_ids.sorted(key=lambda r: (-r.completion_percent, r.user_id.name)):
                rows.append('<tr><td>%s</td><td>%s</td><td style="color:#087f5b">%s</td><td style="color:#b42318">%s</td><td><div style="background:#e6e9ef;height:8px;border-radius:4px;"><div style="background:#087f5b;height:8px;width:%.2f%%;border-radius:4px;"></div></div>%.1f%%</td></tr>' % (escape(line.user_id.name), line.planned_visits, line.completed_visits, line.missed_visits, line.completion_percent, line.completion_percent))
            wizard.comparison_html = '<table class="table table-sm table-striped"><thead><tr><th>Salesperson</th><th>Planned</th><th>Completed</th><th>Missed</th><th>Completion rate</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'

    @api.depends("total_planned_visits", "total_completed_visits", "total_pending_visits", "total_missed_visits", "total_in_progress_visits", "total_overdue_visits", "total_rejected_visits", "total_awaiting_approval_visits")
    def _compute_status_distribution(self):
        for wizard in self:
            items = [("Completed", wizard.total_completed_visits, "#087f5b"), ("Missed", wizard.total_missed_visits, "#dc2626"), ("Pending", wizard.total_pending_visits, "#d97706"), ("In progress", wizard.total_in_progress_visits, "#2563eb"), ("Overdue", wizard.total_overdue_visits, "#b42318"), ("Awaiting approval", wizard.total_awaiting_approval_visits, "#64748b"), ("Rejected", wizard.total_rejected_visits, "#475569")]
            total = wizard.total_planned_visits or 1
            segments = ''.join('<td style="background:%s;width:%.4f%%;height:16px;"></td>' % (color, 100*count/total) for label, count, color in items if count)
            legend = ''.join('<span style="display:inline-block;margin:5px 12px 3px 0;color:%s;font-weight:600;">%s: %s</span>' % (color, label, count) for label, count, color in items)
            wizard.status_distribution_html = '<table style="width:100%;border-collapse:collapse;table-layout:fixed;"><tr>' + segments + '</tr></table><div>' + legend + '</div>'

    def _visit_rows(self, user, plans, trackers, checkins):
        today = fields.Date.context_today(self)
        rows = []
        used = set()
        by_plan = defaultdict(list)
        by_tracker = defaultdict(list)
        for checkin in checkins:
            by_plan[(checkin.tracker_id.plan_id.id, checkin.partner_id.id)].append(checkin)
            by_tracker[(checkin.tracker_id.id, checkin.partner_id.id)].append(checkin)
        def add(partner, date, purpose, plan, target, tracker, candidates, planned):
            matches = [c for c in candidates if c.id not in used and (not c.target_line_id or not target or c.target_line_id == target)]
            matches.sort(key=lambda c: (bool(target and c.target_line_id != target), c.state != "checked_out", c.checkin_time, c.id))
            checkin = matches[0] if matches else False
            if checkin:
                used.add(checkin.id)
                tracker = checkin.tracker_id
                status = "completed" if checkin.state == "checked_out" else ("overdue" if date < today else "in_progress")
                reason = "Check-out recorded" if status == "completed" else "Check-out not recorded"
            elif plan and plan.state == "rejected":
                status, reason = "rejected", "Plan rejected"
            elif plan and plan.state in ("draft", "submitted"):
                status, reason = "awaiting_approval", "Plan not approved"
            elif date < today:
                status, reason = "missed", "No customer check-in recorded by end of visit date"
            else:
                status, reason = "pending", "Scheduled date not yet elapsed"
            visited = tracker.visited_line_ids.filtered(lambda v: checkin and v.checkin_id == checkin)[:1] if tracker else False
            rows.append(dict(user_id=user.id, partner_id=partner.id, visit_date=date, purpose=purpose or False,
                plan_id=plan.id if plan else False, tracker_id=tracker.id if tracker else False,
                checkin_id=checkin.id if checkin else False, is_planned=planned,
                reference=plan.name if plan else (tracker.name if tracker else "Unplanned"),
                status=status, reason=reason, checkin_time=checkin.checkin_time if checkin else False,
                checkout_time=checkin.checkout_time if checkin else False,
                duration_minutes=checkin.duration_minutes if checkin else 0,
                outcome=checkin.meeting_outcome if checkin else False,
                location_name=checkin.location_name if checkin else False,
                checkin_latitude=checkin.checkin_latitude if checkin else 0, checkin_longitude=checkin.checkin_longitude if checkin else 0,
                notes=checkin.notes if checkin else False, customer_feedback=checkin.customer_feedback if checkin else False,
                photo_available=bool(checkin and checkin.with_context(bin_size=True).selfie_image), rating=float(visited.rating) if visited and visited.rating else 0,
                distance_km=tracker.total_distance_km if tracker else 0))
        plan_ids = set(plans.ids)
        for plan in plans:
            for target in plan.target_line_ids:
                for partner in target.customer_ids:
                    if self.partner_id and partner != self.partner_id:
                        continue
                    add(partner, plan.visit_date, plan.purpose, plan, target, False, by_plan[(plan.id, partner.id)], True)
        for tracker in trackers.filtered(lambda t: not t.plan_id or t.plan_id.id not in plan_ids):
            for target in tracker.target_line_ids:
                for partner in target.customer_ids:
                    if self.partner_id and partner != self.partner_id:
                        continue
                    add(partner, tracker.visit_date, tracker.purpose, tracker.plan_id, target.plan_line_id, tracker, by_tracker[(tracker.id, partner.id)], True)
        for checkin in checkins:
            if checkin.id not in used:
                tracker = checkin.tracker_id
                add(checkin.partner_id, tracker.visit_date, tracker.purpose, tracker.plan_id, checkin.target_line_id, tracker, [checkin], False)
        return rows

    def _counts(self, rows):
        planned = [r for r in rows if r["is_planned"]]
        counts = {"planned_visits": len(planned), "completed_visits": sum(r["status"] == "completed" for r in planned), "unplanned_visits": len(rows) - len(planned)}
        for status in ("pending", "missed", "in_progress", "overdue", "awaiting_approval", "rejected"):
            counts[status + "_visits"] = sum(r["status"] == status for r in planned)
        eligible = len(planned) - counts["rejected_visits"] - counts["awaiting_approval_visits"]
        counts["completion_percent"] = 100.0 * counts["completed_visits"] / eligible if eligible else 0.0
        return counts

    def action_generate_report(self):
        self.ensure_one()
        check_report_access(self.env)
        if self.customer_scope == "selected" and not self.partner_id:
            raise ValidationError(_("Please select a customer, or choose All Customers."))
        users = self._selected_users()
        self.line_ids.unlink()
        self.day_line_ids.unlink()
        self.visit_line_ids.unlink()
        all_rows, summaries = [], []
        days = defaultdict(lambda: {"rows": [], "distance_km": 0.0, "visit_minutes": 0.0, "idle_minutes": 0.0})
        for user in users:
            trackers = self.env["salesperson.tracker"].sudo().search(self._tracker_domain_for_user(user))
            plans = self.env["salesperson.visit.plan"].sudo().search(self._plan_domain_for_user(user))
            if self.tracking_status != "all":
                plans = plans.filtered(lambda p: p.id in trackers.mapped("plan_id").ids)
            checkins = self.env["salesperson.checkin"].sudo().search(self._checkin_domain_for_user(user), order="checkin_time,id")
            rows = self._visit_rows(user, plans, trackers, checkins)
            all_rows.extend(rows)
            ratings = [r["rating"] for r in rows if r["rating"]]
            metrics = dict(distance_km=sum(trackers.mapped("total_distance_km")), tracking_minutes=sum(trackers.mapped("total_tracking_time_minutes")), visit_minutes=sum(checkins.filtered(lambda c: c.state == "checked_out").mapped("duration_minutes")), idle_minutes=sum(trackers.mapped("idle_line_ids.duration_minutes")), expense=sum(trackers.mapped("actual_total_cost")), estimated_expense=sum(plans.mapped("total_cost")) + sum(trackers.filtered(lambda t: not t.plan_id or t.plan_id.id not in plans.ids).mapped("total_cost")), average_rating=sum(ratings)/len(ratings) if ratings else 0)
            summaries.append(dict(user_id=user.id, **self._counts(rows), **metrics,
                customer_count=len({r["partner_id"] for r in rows}), visited_customer_count=len({r["partner_id"] for r in rows if r["status"] == "completed"})))
            for row in rows:
                days[row["visit_date"]]["rows"].append(row)
            for tracker in trackers:
                days[tracker.visit_date]["distance_km"] += tracker.total_distance_km
                days[tracker.visit_date]["idle_minutes"] += sum(tracker.idle_line_ids.mapped("duration_minutes"))
            for checkin in checkins.filtered(lambda c: c.state == "checked_out"):
                days[checkin.tracker_id.visit_date]["visit_minutes"] += checkin.duration_minutes
        day_commands = []
        for date, data in sorted(days.items()):
            counts = self._counts(data.pop("rows"))
            counts.pop("completion_percent")
            day_commands.append((0, 0, dict(date=date, **counts, **data)))
        totals = self._counts(all_rows)
        ratings = [r["rating"] for r in all_rows if r["rating"]]
        metric_keys = ("distance_km", "tracking_minutes", "visit_minutes", "idle_minutes", "expense", "estimated_expense")
        self.write(dict(line_ids=[(0, 0, s) for s in summaries], day_line_ids=day_commands,
            visit_line_ids=[(0, 0, r) for r in all_rows if self.visit_status == "all" or r["status"] == self.visit_status],
            total_salespersons=len(users), total_customers=len({r["partner_id"] for r in all_rows}),
            total_visited_customers=len({r["partner_id"] for r in all_rows if r["status"] == "completed"}),
            average_rating=sum(ratings)/len(ratings) if ratings else 0,
            completion_percent=totals.pop("completion_percent"),
            **{"total_" + k: v for k, v in totals.items()},
            **{"total_" + k: sum(s[k] for s in summaries) for k in metric_keys}))
        return {"type": "ir.actions.act_window", "res_model": self._name, "res_id": self.id, "view_mode": "form", "target": "current"}

    def action_reset(self):
        self.ensure_one()
        check_report_access(self.env)
        self.line_ids.unlink()
        self.day_line_ids.unlink()
        self.visit_line_ids.unlink()
        self.write({
            "salesperson_scope": "all",
            "customer_scope": "all",
            "user_ids": [(5, 0, 0)],
            "partner_id": False,
            "sale_team_id": False,
            "visit_status": "all",
            "visit_purpose": "all",
            "tracking_status": "all",
            "total_salespersons": 0,
            "total_customers": 0,
            "total_visited_customers": 0,
            "total_missed_visits": 0,
            "total_in_progress_visits": 0,
            "total_overdue_visits": 0,
            "total_awaiting_approval_visits": 0,
            "total_rejected_visits": 0,
            "total_unplanned_visits": 0,

            "total_planned_visits": 0,
            "total_completed_visits": 0,
            "total_pending_visits": 0,
            "total_distance_km": 0.0,
            "total_tracking_minutes": 0.0,
            "total_visit_minutes": 0.0,
            "total_idle_minutes": 0.0,
            "total_expense": 0.0,
            "total_estimated_expense": 0.0,
            "average_rating": 0.0,
            "completion_percent": 0.0,
        })
        return True

    def action_print_pdf(self):
        self.ensure_one()
        check_report_access(self.env)
        self.action_generate_report()
        return self.env.ref("zencore_salesperson_tracking.action_report_salesperson_performance").report_action(self)

    def action_preview_pdf(self):
        self.ensure_one()
        check_report_access(self.env)
        self.action_generate_report()
        return {
            "type": "ir.actions.client",
            "tag": "zencore_performance_pdf_preview",
            "params": {
                "report_url": "/report/pdf/zencore_salesperson_tracking.report_salesperson_performance_document/%s" % self.id,
                "filename": "Salesperson Performance - %s to %s.pdf" % (self.date_from, self.date_to),
            },
        }

    def action_export_excel(self):
        self.ensure_one()
        check_report_access(self.env)
        self._selected_users()
        return {
            "type": "ir.actions.act_url",
            "url": "/salesperson/performance_report/xlsx/%s" % self.id,
            "target": "self",
        }


class SalespersonPerformanceReportLine(models.TransientModel):
    _name = "salesperson.performance.report.line"
    _description = "Salesperson Performance Summary Line"
    _order = "completed_visits desc, distance_km desc, id"

    wizard_id = fields.Many2one("salesperson.performance.report.wizard", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", string="Salesperson", required=True)
    planned_visits = fields.Integer()
    completed_visits = fields.Integer(string="Completed Planned Visits")
    pending_visits = fields.Integer()
    missed_visits = fields.Integer()
    in_progress_visits = fields.Integer()
    overdue_visits = fields.Integer()
    awaiting_approval_visits = fields.Integer()
    rejected_visits = fields.Integer()
    unplanned_visits = fields.Integer()

    customer_count = fields.Integer(string="Customers in Scope")
    visited_customer_count = fields.Integer(string="Visited Customers")
    completion_percent = fields.Float(string="Completion %")
    distance_km = fields.Float(string="Distance (KM)")
    tracking_minutes = fields.Float(string="Tracking Time (Min)")
    visit_minutes = fields.Float(string="Visit Time (Min)")
    idle_minutes = fields.Float(string="Idle Time (Min)")
    expense = fields.Float(string="Actual Expense")
    estimated_expense = fields.Float(string="Estimated Expense")
    average_rating = fields.Float(string="Avg Rating")


class SalespersonPerformanceReportDayLine(models.TransientModel):
    _name = "salesperson.performance.report.day.line"
    _description = "Salesperson Performance Day Summary"
    _order = "date asc, id asc"

    wizard_id = fields.Many2one("salesperson.performance.report.wizard", required=True, ondelete="cascade")
    date = fields.Date(required=True)
    planned_visits = fields.Integer()
    completed_visits = fields.Integer(string="Completed Planned Visits")
    pending_visits = fields.Integer()
    missed_visits = fields.Integer()
    in_progress_visits = fields.Integer()
    overdue_visits = fields.Integer()
    awaiting_approval_visits = fields.Integer()
    rejected_visits = fields.Integer()
    unplanned_visits = fields.Integer()

    distance_km = fields.Float(string="Distance (KM)")
    visit_minutes = fields.Float(string="Visit Time (Min)")
    idle_minutes = fields.Float(string="Idle Time (Min)")


class SalespersonPerformanceReportVisitLine(models.TransientModel):
    _name = "salesperson.performance.report.visit.line"
    _description = "Salesperson Performance Visit Detail"
    _order = "visit_date asc, checkin_time asc, id asc"

    wizard_id = fields.Many2one("salesperson.performance.report.wizard", required=True, ondelete="cascade")
    visit_date = fields.Date()
    user_id = fields.Many2one("res.users", string="Salesperson")
    partner_id = fields.Many2one("res.partner", string="Customer")
    purpose = fields.Selection([
        ("order", "New Order"), ("payment", "Payment Collection"),
        ("complaint", "Complaint Resolution"), ("followup", "Follow Up"),
        ("demo", "Product Demo"),
    ])
    checkin_time = fields.Datetime(string="Check In")
    checkout_time = fields.Datetime(string="Check Out")
    duration_minutes = fields.Float(string="Duration (Min)")
    distance_km = fields.Float(string="Tracker Distance (KM)")
    plan_id = fields.Many2one("salesperson.visit.plan", string="Visit Plan")
    tracker_id = fields.Many2one("salesperson.tracker", string="Tracking Record")
    checkin_id = fields.Many2one("salesperson.checkin", string="Check-in Record")
    reference = fields.Char(string="Reference")
    is_planned = fields.Boolean(string="Planned")
    reason = fields.Char(string="Status Explanation")
    notes = fields.Text()
    customer_feedback = fields.Text()
    photo_available = fields.Boolean(string="Photo Evidence")
    location_name = fields.Char(string="Check-in Location")
    selfie_image = fields.Binary(related="checkin_id.selfie_image", readonly=True, compute_sudo=False)
    checkin_latitude = fields.Float(digits=(16, 7))
    checkin_longitude = fields.Float(digits=(16, 7))
    status = fields.Selection([("completed", "Completed"), ("in_progress", "In Progress"), ("pending", "Pending"), ("missed", "Missed"), ("overdue", "Overdue"), ("awaiting_approval", "Awaiting Approval"), ("rejected", "Rejected")])
    outcome = fields.Selection([
        ("completed", "Completed"), ("positive", "Positive"), ("neutral", "Neutral"), ("negative", "Negative"),
        ("followup", "Follow-up Needed"), ("deal_closed", "Deal Closed"),
    ])
    rating = fields.Float()
