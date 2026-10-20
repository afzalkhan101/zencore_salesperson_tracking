from calendar import monthrange
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalespersonPerformanceReportWizard(models.TransientModel):
    _name = "salesperson.performance.report.wizard"
    _description = "Salesperson Performance Report"

    report_type = fields.Selection([
        ("monthly", "Monthly Report"),
        ("weekly", "Weekly Report"),
        ("individual", "Individual Salesperson"),
        ("multiple", "Multiple Salespersons"),
    ], required=True, default="monthly", string="Report Type")

    month_date = fields.Date(string="Month", default=lambda self: fields.Date.context_today(self).replace(day=1))
    week_start = fields.Date(string="Week Start", default=lambda self: self._default_week_start())
    period_preset = fields.Selection([
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
    sale_team_id = fields.Many2one("crm.team", string="Sales Team")
    partner_id = fields.Many2one("res.partner", string="Customer")
    visit_status = fields.Selection([
        ("all", "All"),
        ("completed", "Completed"),
        ("pending", "Pending"),
    ], default="all", required=True, string="Visit Status")
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

    total_salespersons = fields.Integer(readonly=True)
    total_planned_visits = fields.Integer(readonly=True)
    total_completed_visits = fields.Integer(readonly=True)
    total_pending_visits = fields.Integer(readonly=True)
    total_distance_km = fields.Float(readonly=True)
    total_tracking_minutes = fields.Float(readonly=True)
    total_visit_minutes = fields.Float(readonly=True)
    total_idle_minutes = fields.Float(readonly=True)
    total_expense = fields.Float(readonly=True)
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
            if preset == "this_week":
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

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("From Date cannot be after To Date."))

    def _selected_users(self):
        self.ensure_one()
        User = self.env["res.users"].sudo()
        if self.report_type == "individual":
            if not self.individual_user_id:
                raise ValidationError(_("Please select a salesperson for the Individual report."))
            users = self.individual_user_id
        elif self.report_type == "multiple":
            if not self.user_ids:
                raise ValidationError(_("Please select at least one salesperson for the Multiple Salespersons report."))
            users = self.user_ids
        else:
            users = self.user_ids or User.search([("salesperson_role", "=", "salesman"), ("active", "=", True)])
        if self.sale_team_id:
            users = users.filtered(lambda u: u.sale_team_id == self.sale_team_id)
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

    def _user_stats(self, user):
        Tracker = self.env["salesperson.tracker"].sudo()
        Plan = self.env["salesperson.visit.plan"].sudo()
        Checkin = self.env["salesperson.checkin"].sudo()
        trackers = Tracker.search(self._tracker_domain_for_user(user))
        plans = Plan.search(self._plan_domain_for_user(user))
        checkins = Checkin.search(self._checkin_domain_for_user(user))

        completed_checkins = checkins.filtered(lambda c: c.state == "checked_out")
        if self.visit_status == "completed":
            checkins = completed_checkins
        elif self.visit_status == "pending":
            checkins = Checkin.browse()

        planned = sum(plans.mapped("total_visits"))
        plan_ids = set(plans.ids)
        for tracker in trackers.filtered(lambda t: not t.plan_id or t.plan_id.id not in plan_ids):
            planned += tracker.total_visits
        completed = len(completed_checkins)
        pending = max(planned - completed, 0)

        if self.visit_status == "completed":
            planned_display, pending_display = completed, 0
        elif self.visit_status == "pending":
            completed, planned_display = 0, pending
            pending_display = pending
        else:
            planned_display, pending_display = planned, pending

        ratings = []
        visited_lines = trackers.mapped("visited_line_ids")
        if self.partner_id:
            visited_lines = visited_lines.filtered(lambda v: v.partner_id == self.partner_id)
        for rating in visited_lines.mapped("rating"):
            if rating:
                try:
                    ratings.append(float(rating))
                except (TypeError, ValueError):
                    pass

        distance = sum(trackers.mapped("total_distance_km"))
        tracking_minutes = sum(trackers.mapped("total_tracking_time_minutes"))
        visit_minutes = sum(completed_checkins.mapped("duration_minutes"))
        idle_minutes = sum(trackers.mapped("idle_line_ids").mapped("duration_minutes"))
        expense = sum(trackers.mapped("actual_total_cost"))
        avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
        completion = (completed / planned * 100.0) if planned else (100.0 if completed else 0.0)

        return {
            "user": user,
            "trackers": trackers,
            "plans": plans,
            "checkins": checkins,
            "planned": planned_display,
            "completed": completed,
            "pending": pending_display,
            "completion": completion,
            "distance": distance,
            "tracking_minutes": tracking_minutes,
            "visit_minutes": visit_minutes,
            "idle_minutes": idle_minutes,
            "expense": expense,
            "avg_rating": avg_rating,
        }

    def action_generate_report(self):
        self.ensure_one()
        users = self._selected_users()
        self.line_ids.unlink()
        self.day_line_ids.unlink()
        self.visit_line_ids.unlink()

        summary_commands = []
        visit_commands = []
        all_stats = []

        for user in users:
            stats = self._user_stats(user)
            all_stats.append(stats)
            summary_commands.append((0, 0, {
                "user_id": user.id,
                "planned_visits": stats["planned"],
                "completed_visits": stats["completed"],
                "pending_visits": stats["pending"],
                "completion_percent": stats["completion"],
                "distance_km": stats["distance"],
                "tracking_minutes": stats["tracking_minutes"],
                "visit_minutes": stats["visit_minutes"],
                "idle_minutes": stats["idle_minutes"],
                "expense": stats["expense"],
                "average_rating": stats["avg_rating"],
            }))

            checkins = self.env["salesperson.checkin"].sudo().search(self._checkin_domain_for_user(user), order="checkin_time asc, id asc")
            if self.visit_status == "completed":
                checkins = checkins.filtered(lambda c: c.state == "checked_out")
            elif self.visit_status == "pending":
                checkins = self.env["salesperson.checkin"].browse()
            for checkin in checkins:
                visited = self.env["salesperson.tracker.visited.line"].sudo().search([("checkin_id", "=", checkin.id)], limit=1)
                visit_commands.append((0, 0, {
                    "visit_date": checkin.tracker_id.visit_date,
                    "user_id": user.id,
                    "partner_id": checkin.partner_id.id,
                    "purpose": checkin.tracker_id.purpose or False,
                    "checkin_time": checkin.checkin_time,
                    "checkout_time": checkin.checkout_time,
                    "duration_minutes": checkin.duration_minutes,
                    "distance_km": checkin.tracker_id.total_distance_km,
                    "status": "completed" if checkin.state == "checked_out" else "in_progress",
                    "outcome": checkin.meeting_outcome or False,
                    "rating": float(visited.rating) if visited and visited.rating else 0.0,
                }))

        # Day-wise summary, useful for weekly/monthly views.
        day = self.date_from
        day_commands = []
        while day <= self.date_to:
            day_planned = day_completed = 0
            day_distance = day_visit = day_idle = 0.0
            for user in users:
                plans = self.env["salesperson.visit.plan"].sudo().search(self._plan_domain_for_user(user) + [("visit_date", "=", day)])
                trackers = self.env["salesperson.tracker"].sudo().search(self._tracker_domain_for_user(user) + [("visit_date", "=", day)])
                checkins = self.env["salesperson.checkin"].sudo().search(self._checkin_domain_for_user(user) + [("tracker_id.visit_date", "=", day)])
                day_planned += sum(plans.mapped("total_visits"))
                day_completed += len(checkins.filtered(lambda c: c.state == "checked_out"))
                day_distance += sum(trackers.mapped("total_distance_km"))
                day_visit += sum(checkins.filtered(lambda c: c.state == "checked_out").mapped("duration_minutes"))
                day_idle += sum(trackers.mapped("idle_line_ids").mapped("duration_minutes"))
            if day_planned or day_completed or day_distance or day_visit or day_idle:
                day_commands.append((0, 0, {
                    "date": day,
                    "planned_visits": day_planned,
                    "completed_visits": day_completed,
                    "pending_visits": max(day_planned - day_completed, 0),
                    "distance_km": day_distance,
                    "visit_minutes": day_visit,
                    "idle_minutes": day_idle,
                }))
            day += timedelta(days=1)

        total_planned = sum(s["planned"] for s in all_stats)
        total_completed = sum(s["completed"] for s in all_stats)
        total_pending = sum(s["pending"] for s in all_stats)
        ratings = [s["avg_rating"] for s in all_stats if s["avg_rating"]]
        vals = {
            "line_ids": summary_commands,
            "day_line_ids": day_commands,
            "visit_line_ids": visit_commands,
            "total_salespersons": len(users),
            "total_planned_visits": total_planned,
            "total_completed_visits": total_completed,
            "total_pending_visits": total_pending,
            "total_distance_km": sum(s["distance"] for s in all_stats),
            "total_tracking_minutes": sum(s["tracking_minutes"] for s in all_stats),
            "total_visit_minutes": sum(s["visit_minutes"] for s in all_stats),
            "total_idle_minutes": sum(s["idle_minutes"] for s in all_stats),
            "total_expense": sum(s["expense"] for s in all_stats),
            "average_rating": sum(ratings) / len(ratings) if ratings else 0.0,
            "completion_percent": (total_completed / total_planned * 100.0) if total_planned else (100.0 if total_completed else 0.0),
        }
        self.write(vals)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_reset(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.day_line_ids.unlink()
        self.visit_line_ids.unlink()
        self.write({
            "total_salespersons": 0,
            "total_planned_visits": 0,
            "total_completed_visits": 0,
            "total_pending_visits": 0,
            "total_distance_km": 0.0,
            "total_tracking_minutes": 0.0,
            "total_visit_minutes": 0.0,
            "total_idle_minutes": 0.0,
            "total_expense": 0.0,
            "average_rating": 0.0,
            "completion_percent": 0.0,
        })
        return True

    def action_print_pdf(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_generate_report()
        return self.env.ref("zencore_salesperson_tracking.action_report_salesperson_performance").report_action(self)

    def action_export_excel(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_generate_report()
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
    completed_visits = fields.Integer()
    pending_visits = fields.Integer()
    completion_percent = fields.Float(string="Completion %")
    distance_km = fields.Float(string="Distance (KM)")
    tracking_minutes = fields.Float(string="Tracking Time (Min)")
    visit_minutes = fields.Float(string="Visit Time (Min)")
    idle_minutes = fields.Float(string="Idle Time (Min)")
    expense = fields.Float(string="Expense")
    average_rating = fields.Float(string="Avg Rating")


class SalespersonPerformanceReportDayLine(models.TransientModel):
    _name = "salesperson.performance.report.day.line"
    _description = "Salesperson Performance Day Summary"
    _order = "date asc, id asc"

    wizard_id = fields.Many2one("salesperson.performance.report.wizard", required=True, ondelete="cascade")
    date = fields.Date(required=True)
    planned_visits = fields.Integer()
    completed_visits = fields.Integer()
    pending_visits = fields.Integer()
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
    status = fields.Selection([("completed", "Completed"), ("in_progress", "In Progress")])
    outcome = fields.Selection([
        ("positive", "Positive"), ("neutral", "Neutral"), ("negative", "Negative"),
        ("followup", "Follow-up Needed"), ("deal_closed", "Deal Closed"),
    ])
    rating = fields.Float()
