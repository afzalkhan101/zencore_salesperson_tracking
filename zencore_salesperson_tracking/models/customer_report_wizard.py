from calendar import monthrange
from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .report_security import check_report_access, report_team_user_ids


class SalespersonCustomerReportWizard(models.TransientModel):
    """Customer-focused counterpart to the performance-report wizard.

    It shares the performance report's period, scope, and hierarchy rules while
    keeping the generated summaries centred on customers and their visits.
    """

    _name = "salesperson.customer.report.wizard"
    _description = "Customer Visit Report"
    _rec_name = "name"

    name = fields.Char(default=lambda self: _("Customer Visit Report"), readonly=True, required=True)

    report_type = fields.Selection([
        ("monthly", "Monthly Report"),
        ("weekly", "Weekly Report"),
        ("individual", "Individual Salesperson"),
        ("multiple", "Multiple Salespersons"),
    ], required=True, default="monthly", string="Report Type")
    month_date = fields.Date(string="Month", default=lambda self: fields.Date.context_today(self).replace(day=1))
    week_start = fields.Date(string="Week Start", default=lambda self: self._default_week_start())
    period_preset = fields.Selection([
        ("today", "Today"), ("this_week", "This Week"),
        ("last_week", "Last Week"), ("this_month", "This Month"),
        ("last_month", "Last Month"), ("custom", "Custom Range"),
    ], string="Period", default="this_month")
    date_from = fields.Date(string="From Date", required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string="To Date", required=True, default=fields.Date.context_today)

    individual_user_id = fields.Many2one(
        "res.users", string="Salesperson", domain="[('salesperson_role', '=', 'salesman')]",
    )
    user_ids = fields.Many2many(
        "res.users", "salesperson_customer_report_user_rel", "wizard_id", "user_id",
        string="Salespersons", domain="[('salesperson_role', '=', 'salesman')]",
    )
    salesperson_scope = fields.Selection([
        ("all", "All Salespersons"), ("selected", "Selected Salespersons"),
    ], string="Salespersons", required=True, default="all")
    customer_scope = fields.Selection([
        ("all", "All Customers"), ("selected", "Selected Customer"),
    ], string="Customer", required=True, default="all")
    partner_id = fields.Many2one(
        "res.partner", string="Customer",
        domain="[('active', '=', True), ('customer_rank', '>', 0), ('user_ids', '=', False)]",
    )
    visit_status = fields.Selection([
        ("all", "All"), ("completed", "Completed"), ("pending", "Pending"),
        ("missed", "Missed"), ("in_progress", "In Progress"),
        ("overdue", "Overdue"), ("awaiting_approval", "Awaiting Approval"),
        ("rejected", "Rejected"),
    ], string="Visit Status", required=True, default="all")
    visit_purpose = fields.Selection([
        ("all", "All"), ("order", "New Order"),
        ("payment", "Payment Collection"), ("complaint", "Complaint Resolution"),
        ("followup", "Follow Up"), ("demo", "Product Demo"),
    ], string="Visit Purpose", required=True, default="all")
    tracking_status = fields.Selection([
        ("all", "All"), ("planned", "Planned"), ("live", "Live"),
        ("offline", "Offline"), ("completed", "Completed"),
    ], string="Tracking Status", required=True, default="all")

    line_ids = fields.One2many("salesperson.customer.report.line", "wizard_id", string="Visit Details", readonly=True)
    customer_line_ids = fields.One2many("salesperson.customer.report.summary.line", "wizard_id", string="Customer Summary", readonly=True)
    day_line_ids = fields.One2many("salesperson.customer.report.day.line", "wizard_id", string="Daily Summary", readonly=True)

    total_customers = fields.Integer(readonly=True)
    total_salespersons = fields.Integer(readonly=True)
    total_visits = fields.Integer(string="Planned Visits", readonly=True)
    completed_visits = fields.Integer(readonly=True)
    pending_visits = fields.Integer(string="Remaining Visits", readonly=True)
    missed_visits = fields.Integer(readonly=True)
    in_progress_visits = fields.Integer(readonly=True)
    completion_percent = fields.Float(readonly=True)
    total_distance_km = fields.Float(readonly=True)
    total_tracking_minutes = fields.Float(readonly=True)
    total_visit_minutes = fields.Float(readonly=True)
    total_idle_minutes = fields.Float(readonly=True)
    total_expense = fields.Float(readonly=True)
    average_rating = fields.Float(readonly=True)

    @api.model
    def _default_date_from(self):
        return fields.Date.context_today(self).replace(day=1)

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
            start = (self.week_start or today) - timedelta(days=(self.week_start or today).weekday())
            self.week_start = start
            self.date_from, self.date_to = start, start + timedelta(days=6)
        else:
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
                previous_last_day = today.replace(day=1) - timedelta(days=1)
                self.date_from = previous_last_day.replace(day=1)
                self.date_to = previous_last_day

    @api.onchange("salesperson_scope")
    def _onchange_salesperson_scope(self):
        if self.salesperson_scope == "all":
            self.user_ids = [(5, 0, 0)]

    @api.onchange("user_ids")
    def _onchange_users(self):
        if self.user_ids and self.report_type != "individual":
            self.salesperson_scope = "selected"

    @api.onchange("customer_scope")
    def _onchange_customer_scope(self):
        if self.customer_scope == "all":
            self.partner_id = False

    @api.onchange("partner_id")
    def _onchange_partner(self):
        if self.partner_id:
            self.customer_scope = "selected"

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("From Date cannot be after To Date."))

    def _selected_users(self):
        self.ensure_one()
        check_report_access(self.env)
        permitted = set(report_team_user_ids(self.env))
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
                ("id", "in", list(permitted)), ("salesperson_role", "=", "salesman"), ("active", "=", True),
            ])
        if any(user.id not in permitted for user in users):
            raise AccessError(_("Selected users must belong to your reporting hierarchy."))
        return users

    def _plan_domain_for_user(self, user):
        domain = [("user_id", "=", user.id), ("visit_date", ">=", self.date_from), ("visit_date", "<=", self.date_to)]
        if self.partner_id:
            domain.append(("target_line_ids.customer_ids", "in", self.partner_id.id))
        if self.visit_purpose != "all":
            domain.append(("purpose", "=", self.visit_purpose))
        return domain

    def _tracker_domain_for_user(self, user):
        domain = [("user_id", "=", user.id), ("visit_date", ">=", self.date_from), ("visit_date", "<=", self.date_to)]
        if self.partner_id:
            domain += ["|", ("target_line_ids.customer_ids", "in", self.partner_id.id), ("visited_line_ids.partner_id", "=", self.partner_id.id)]
        if self.visit_purpose != "all":
            domain.append(("purpose", "=", self.visit_purpose))
        if self.tracking_status != "all":
            domain.append(("state", "=", self.tracking_status))
        return domain

    def _checkin_domain_for_user(self, user):
        domain = [("user_id", "=", user.id), ("tracker_id.visit_date", ">=", self.date_from), ("tracker_id.visit_date", "<=", self.date_to)]
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        if self.visit_purpose != "all":
            domain.append(("tracker_id.purpose", "=", self.visit_purpose))
        if self.tracking_status != "all":
            domain.append(("tracker_id.state", "=", self.tracking_status))
        return domain

    def _visit_rows(self, user, plans, trackers, checkins):
        """Return one row per plan customer, plus unplanned check-ins.

        Status semantics deliberately match the performance report so a visit is
        completed only after a recorded check-out.
        """
        today = fields.Date.context_today(self)
        rows, used_checkins = [], set()
        by_plan, by_tracker = defaultdict(list), defaultdict(list)
        for checkin in checkins:
            by_plan[(checkin.tracker_id.plan_id.id, checkin.partner_id.id)].append(checkin)
            by_tracker[(checkin.tracker_id.id, checkin.partner_id.id)].append(checkin)

        def add(partner, visit_date, purpose, plan, target, tracker, candidates, planned):
            if self.partner_id and partner != self.partner_id:
                return
            matches = [checkin for checkin in candidates if checkin.id not in used_checkins and (not checkin.target_line_id or not target or checkin.target_line_id == target)]
            matches.sort(key=lambda c: (bool(target and c.target_line_id != target), c.state != "checked_out", c.checkin_time, c.id))
            checkin = matches[0] if matches else False
            if checkin:
                used_checkins.add(checkin.id)
                tracker = checkin.tracker_id
                status = "completed" if checkin.state == "checked_out" else ("overdue" if visit_date < today else "in_progress")
                reason = "Check-out recorded" if status == "completed" else "Check-out not recorded"
            elif plan and plan.state == "rejected":
                status, reason = "rejected", "Plan rejected"
            elif plan and plan.state in ("draft", "submitted"):
                status, reason = "awaiting_approval", "Plan not approved"
            elif visit_date < today:
                status, reason = "missed", "No customer check-in recorded by end of visit date"
            else:
                status, reason = "pending", "Scheduled date not yet elapsed"
            visited = tracker.visited_line_ids.filtered(lambda line: checkin and line.checkin_id == checkin)[:1] if tracker else False
            rows.append({
                "partner_id": partner.id, "user_id": user.id, "visit_date": visit_date, "purpose": purpose or False,
                "plan_id": plan.id if plan else False, "tracker_id": tracker.id if tracker else False,
                "checkin_id": checkin.id if checkin else False, "is_planned": planned,
                "visit_plan_ref": plan.name if plan else (tracker.name if tracker else _("Unplanned")),
                "status": status, "reason": reason, "checkin_time": checkin.checkin_time if checkin else False,
                "checkout_time": checkin.checkout_time if checkin else False,
                "duration_minutes": checkin.duration_minutes if checkin else 0.0,
                "outcome": checkin.meeting_outcome if checkin else False,
                "notes": checkin.notes if checkin else False,
                "customer_feedback": checkin.customer_feedback if checkin else False,
                "rating": float(visited.rating) if visited and visited.rating else 0.0,
                "distance_km": tracker.total_distance_km if tracker else 0.0,
            })

        plan_ids = set(plans.ids)
        for plan in plans:
            for target in plan.target_line_ids:
                for partner in target.customer_ids:
                    add(partner, plan.visit_date, plan.purpose, plan, target, False, by_plan[(plan.id, partner.id)], True)
        for tracker in trackers.filtered(lambda record: not record.plan_id or record.plan_id.id not in plan_ids):
            for target in tracker.target_line_ids:
                for partner in target.customer_ids:
                    add(partner, tracker.visit_date, tracker.purpose, tracker.plan_id, target.plan_line_id, tracker, by_tracker[(tracker.id, partner.id)], True)
        for checkin in checkins:
            if checkin.id not in used_checkins:
                tracker = checkin.tracker_id
                add(checkin.partner_id, tracker.visit_date, tracker.purpose, tracker.plan_id, checkin.target_line_id, tracker, [checkin], False)
        return rows

    @staticmethod
    def _counts(rows):
        planned = [row for row in rows if row["is_planned"]]
        completed = sum(row["status"] == "completed" for row in planned)
        pending = sum(row["status"] == "pending" for row in planned)
        in_progress = sum(row["status"] == "in_progress" for row in planned)
        missed = sum(row["status"] in ("missed", "overdue") for row in planned)
        eligible = len(planned) - sum(row["status"] in ("rejected", "awaiting_approval") for row in planned)
        return {"planned": len(planned), "completed": completed, "pending": pending, "in_progress": in_progress, "missed": missed, "completion_percent": 100.0 * completed / eligible if eligible else 0.0}

    def action_generate_report(self):
        self.ensure_one()
        check_report_access(self.env)
        if self.customer_scope == "selected" and not self.partner_id:
            raise ValidationError(_("Please select a customer, or choose All Customers."))
        self._check_date_range()
        users = self._selected_users()
        self.line_ids.unlink()
        self.customer_line_ids.unlink()
        self.day_line_ids.unlink()

        all_rows, all_trackers, all_checkins = [], self.env["salesperson.tracker"], self.env["salesperson.checkin"]
        for user in users:
            trackers = self.env["salesperson.tracker"].sudo().search(self._tracker_domain_for_user(user))
            plans = self.env["salesperson.visit.plan"].sudo().search(self._plan_domain_for_user(user))
            if self.tracking_status != "all":
                plans = plans.filtered(lambda plan: plan.id in trackers.mapped("plan_id").ids)
            checkins = self.env["salesperson.checkin"].sudo().search(self._checkin_domain_for_user(user), order="checkin_time,id")
            all_rows.extend(self._visit_rows(user, plans, trackers, checkins))
            all_trackers |= trackers
            all_checkins |= checkins

        visible_rows = [row for row in all_rows if self.visit_status == "all" or row["status"] == self.visit_status]
        customer_buckets, day_buckets = defaultdict(list), defaultdict(list)
        for row in all_rows:
            customer_buckets[row["partner_id"]].append(row)
            day_buckets[row["visit_date"]].append(row)
        customer_commands = []
        for partner_id, rows in sorted(customer_buckets.items(), key=lambda pair: self.env["res.partner"].browse(pair[0]).display_name or ""):
            counts = self._counts(rows)
            trackers = self.env["salesperson.tracker"].browse(list({row["tracker_id"] for row in rows if row["tracker_id"]}))
            customer_commands.append((0, 0, {"partner_id": partner_id, **counts,
                "salesperson_count": len({row["user_id"] for row in rows}),
                "distance_km": sum(trackers.mapped("total_distance_km")),
                "visit_minutes": sum(row["duration_minutes"] for row in rows if row["status"] == "completed"),
                "last_visit_date": max((row["visit_date"] for row in rows if row["status"] == "completed"), default=False)}))
        day_commands = []
        for visit_date, rows in sorted(day_buckets.items()):
            counts = self._counts(rows)
            trackers = self.env["salesperson.tracker"].browse(list({row["tracker_id"] for row in rows if row["tracker_id"]}))
            day_commands.append((0, 0, {"date": visit_date, **counts,
                "distance_km": sum(trackers.mapped("total_distance_km")),
                "visit_minutes": sum(row["duration_minutes"] for row in rows if row["status"] == "completed")}))
        totals = self._counts(all_rows)
        summary_trackers = all_trackers.filtered(lambda tracker: tracker.id in {row["tracker_id"] for row in all_rows if row["tracker_id"]})
        ratings = [row["rating"] for row in all_rows if row["rating"]]
        self.write({
            "line_ids": [(0, 0, row) for row in visible_rows], "customer_line_ids": customer_commands, "day_line_ids": day_commands,
            "total_customers": len(customer_buckets), "total_salespersons": len(users), "total_visits": totals["planned"],
            "completed_visits": totals["completed"], "pending_visits": totals["pending"], "missed_visits": totals["missed"],
            "in_progress_visits": totals["in_progress"], "completion_percent": totals["completion_percent"],
            "total_distance_km": sum(summary_trackers.mapped("total_distance_km")),
            "total_tracking_minutes": sum(summary_trackers.mapped("total_tracking_time_minutes")),
            "total_visit_minutes": sum(all_checkins.filtered(lambda checkin: checkin.state == "checked_out").mapped("duration_minutes")),
            "total_idle_minutes": sum(summary_trackers.mapped("idle_line_ids.duration_minutes")),
            "total_expense": sum(summary_trackers.mapped("actual_total_cost")),
            "average_rating": sum(ratings) / len(ratings) if ratings else 0.0,
        })
        return True

    def action_reset(self):
        self.ensure_one()
        check_report_access(self.env)
        today = fields.Date.context_today(self)
        self.write({
            "report_type": "monthly", "month_date": today.replace(day=1), "week_start": today - timedelta(days=today.weekday()), "period_preset": "this_month", "date_from": today.replace(day=1), "date_to": today,
            "individual_user_id": False, "salesperson_scope": "all", "user_ids": [(5, 0, 0)], "customer_scope": "all", "partner_id": False, "visit_status": "all", "visit_purpose": "all", "tracking_status": "all",
            "line_ids": [(5, 0, 0)], "customer_line_ids": [(5, 0, 0)], "day_line_ids": [(5, 0, 0)], "total_customers": 0, "total_salespersons": 0, "total_visits": 0, "completed_visits": 0, "pending_visits": 0, "missed_visits": 0, "in_progress_visits": 0, "completion_percent": 0.0, "total_distance_km": 0.0, "total_tracking_minutes": 0.0, "total_visit_minutes": 0.0, "total_idle_minutes": 0.0, "total_expense": 0.0, "average_rating": 0.0,
        })
        return True

    def action_print_pdf(self):
        self.ensure_one()
        check_report_access(self.env)
        self.action_generate_report()
        return self.env.ref("zencore_salesperson_tracking.action_report_customer_detailed").report_action(self)

    def action_preview_pdf(self):
        self.ensure_one()
        check_report_access(self.env)
        self.action_generate_report()
        return {"type": "ir.actions.client", "tag": "zencore_customer_pdf_preview", "params": {
            "report_url": "/report/pdf/zencore_salesperson_tracking.report_customer_detailed_document/%s" % self.id,
            "filename": "Customer Visit Report - %s to %s.pdf" % (self.date_from, self.date_to)}}

    def action_export_excel(self):
        self.ensure_one()
        check_report_access(self.env)
        self._selected_users()
        return {"type": "ir.actions.act_url", "url": "/salesperson/customer_report/xlsx/%s" % self.id, "target": "self"}


class SalespersonCustomerReportLine(models.TransientModel):
    _name = "salesperson.customer.report.line"
    _description = "Customer Visit Report Detail"
    _order = "visit_date asc, checkin_time asc, id asc"

    wizard_id = fields.Many2one("salesperson.customer.report.wizard", required=True, ondelete="cascade")
    plan_id = fields.Many2one("salesperson.visit.plan", readonly=True)
    tracker_id = fields.Many2one("salesperson.tracker", readonly=True)
    checkin_id = fields.Many2one("salesperson.checkin", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Customer", readonly=True)
    visit_date = fields.Date(readonly=True)
    visit_plan_ref = fields.Char(string="Reference", readonly=True)
    user_id = fields.Many2one("res.users", string="Salesperson", readonly=True)
    purpose = fields.Selection(selection=lambda self: self.env["salesperson.visit.plan"]._fields["purpose"].selection, readonly=True)
    is_planned = fields.Boolean(readonly=True)
    checkin_time = fields.Datetime(string="Check In", readonly=True)
    checkout_time = fields.Datetime(string="Check Out", readonly=True)
    duration_minutes = fields.Float(string="Duration (Min)", readonly=True)
    distance_km = fields.Float(string="Distance (KM)", readonly=True)
    status = fields.Selection([
        ("completed", "Completed"), ("pending", "Pending"), ("missed", "Missed"), ("in_progress", "In Progress"), ("overdue", "Overdue"), ("awaiting_approval", "Awaiting Approval"), ("rejected", "Rejected"),
    ], readonly=True)
    reason = fields.Char(readonly=True)
    outcome = fields.Selection(selection=lambda self: self.env["salesperson.checkin"]._fields["meeting_outcome"].selection, readonly=True)
    rating = fields.Float(readonly=True)
    notes = fields.Text(readonly=True)
    customer_feedback = fields.Text(readonly=True)


class SalespersonCustomerReportSummaryLine(models.TransientModel):
    _name = "salesperson.customer.report.summary.line"
    _description = "Customer Visit Report Customer Summary"
    _order = "partner_id"

    wizard_id = fields.Many2one("salesperson.customer.report.wizard", required=True, ondelete="cascade")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True, readonly=True)
    salesperson_count = fields.Integer(string="Salespersons", readonly=True)
    planned = fields.Integer(readonly=True)
    completed = fields.Integer(readonly=True)
    pending = fields.Integer(readonly=True)
    in_progress = fields.Integer(readonly=True)
    missed = fields.Integer(readonly=True)
    completion_percent = fields.Float(string="Completion %", readonly=True)
    distance_km = fields.Float(string="Distance (KM)", readonly=True)
    visit_minutes = fields.Float(string="Visit Time (Min)", readonly=True)
    last_visit_date = fields.Date(string="Last Completed Visit", readonly=True)


class SalespersonCustomerReportDayLine(models.TransientModel):
    _name = "salesperson.customer.report.day.line"
    _description = "Customer Visit Report Day Summary"
    _order = "date asc, id asc"

    wizard_id = fields.Many2one("salesperson.customer.report.wizard", required=True, ondelete="cascade")
    date = fields.Date(required=True, readonly=True)
    planned = fields.Integer(readonly=True)
    completed = fields.Integer(readonly=True)
    pending = fields.Integer(readonly=True)
    in_progress = fields.Integer(readonly=True)
    missed = fields.Integer(readonly=True)
    completion_percent = fields.Float(string="Completion %", readonly=True)
    distance_km = fields.Float(string="Distance (KM)", readonly=True)
    visit_minutes = fields.Float(string="Visit Time (Min)", readonly=True)
