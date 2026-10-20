from datetime import date
from calendar import monthrange

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalespersonCustomerReportWizard(models.TransientModel):
    _name = "salesperson.customer.report.wizard"
    _description = "Customer Detailed Visit Report"

    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
    )
    user_id = fields.Many2one("res.users", string="Salesperson")
    date_from = fields.Date(string="From Date", required=True, default=lambda self: self._default_date_from())
    date_to = fields.Date(string="To Date", required=True, default=fields.Date.context_today)
    visit_status = fields.Selection(
        [
            ("all", "All"),
            ("completed", "Completed"),
            ("pending", "Planned / Pending"),
        ],
        string="Visit Status",
        required=True,
        default="all",
    )

    line_ids = fields.One2many(
        "salesperson.customer.report.line",
        "wizard_id",
        string="Report Preview",
        readonly=True,
    )

    total_visits = fields.Integer(string="Total Visits", readonly=True)
    completed_visits = fields.Integer(string="Completed Visits", readonly=True)
    pending_visits = fields.Integer(string="Planned / Pending", readonly=True)
    total_distance_km = fields.Float(string="Total Distance (KM)", readonly=True)
    total_visit_minutes = fields.Float(string="Total Visit Time (Min)", readonly=True)
    total_expense = fields.Float(string="Total Expense", readonly=True)
    average_rating = fields.Float(string="Average Rating", readonly=True)

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1)

    @api.constrains("date_from", "date_to")
    def _check_date_range(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(_("From Date cannot be after To Date."))

    def _tracker_domain(self):
        self.ensure_one()
        domain = [
            ("visit_date", ">=", self.date_from),
            ("visit_date", "<=", self.date_to),
        ]
        if self.user_id:
            domain.append(("user_id", "=", self.user_id.id))
        return domain

    def _plan_domain(self):
        self.ensure_one()
        domain = [
            ("visit_date", ">=", self.date_from),
            ("visit_date", "<=", self.date_to),
            ("target_line_ids.customer_ids", "in", self.partner_id.id),
        ]
        if self.user_id:
            domain.append(("user_id", "=", self.user_id.id))
        return domain

    def _get_relevant_trackers(self):
        self.ensure_one()
        trackers = self.env["salesperson.tracker"].search(
            self._tracker_domain(), order="visit_date asc, id asc"
        )
        partner = self.partner_id
        return trackers.filtered(
            lambda tracker: partner in tracker.target_line_ids.mapped("customer_ids")
            or partner in tracker.visited_line_ids.mapped("partner_id")
            or partner in self.env["salesperson.checkin"].search([
                ("tracker_id", "=", tracker.id),
                ("partner_id", "=", partner.id),
            ]).mapped("partner_id")
        )

    def _prepare_report_rows(self):
        """Build customer-wise rows from Visit Plans first, then add any
        tracker/check-in records that are not linked to those plans.

        The old implementation started only from salesperson.tracker. That
        meant a perfectly valid planned customer disappeared from the report
        until somebody clicked On Track and created a tracker. Customer reports
        must also show planned/pending visits, so Visit Plan is the authoritative
        source for planned rows while Check-In is the authoritative source for
        actual visits.
        """
        self.ensure_one()
        rows = []
        seen_checkin_ids = set()
        seen_plan_ids = set()
        partner = self.partner_id

        plans = self.env["salesperson.visit.plan"].search(
            self._plan_domain(), order="visit_date asc, id asc"
        )

        # 1) Planned customer visits (works even before a tracker exists).
        for plan in plans:
            seen_plan_ids.add(plan.id)
            tracker = self.env["salesperson.tracker"].search([
                ("plan_id", "=", plan.id),
            ], order="id desc", limit=1)

            checkins = self.env["salesperson.checkin"]
            if tracker:
                checkins = self.env["salesperson.checkin"].search([
                    ("tracker_id", "=", tracker.id),
                    ("partner_id", "=", partner.id),
                ], order="checkin_time asc, id asc")

            if checkins:
                if self.visit_status == "pending":
                    continue
                for checkin in checkins:
                    seen_checkin_ids.add(checkin.id)
                    visited_line = self.env["salesperson.tracker.visited.line"].search([
                        ("checkin_id", "=", checkin.id),
                    ], limit=1)
                    rating = int(visited_line.rating or 0) if visited_line else 0
                    rows.append({
                        "plan": plan,
                        "tracker": tracker,
                        "checkin": checkin,
                        "visited_line": visited_line,
                        "visit_date": plan.visit_date,
                        "user": plan.user_id,
                        "purpose": plan.purpose,
                        "visit_plan_ref": plan.name or "",
                        "status": "completed" if checkin.state == "checked_out" else "in_progress",
                        "status_label": "Completed" if checkin.state == "checked_out" else "In Progress",
                        "rating": rating,
                    })
            else:
                if self.visit_status == "completed":
                    continue
                rows.append({
                    "plan": plan,
                    "tracker": tracker,
                    "checkin": False,
                    "visited_line": False,
                    "visit_date": plan.visit_date,
                    "user": plan.user_id,
                    "purpose": plan.purpose,
                    "visit_plan_ref": plan.name or "",
                    "status": "pending",
                    "status_label": "Planned / Pending",
                    "rating": 0,
                })

        # 2) Actual check-ins/tracker rows that may not be linked to a Visit Plan
        #    (legacy/manual data). Do not duplicate anything already added above.
        checkin_domain = [
            ("partner_id", "=", partner.id),
            ("tracker_id.visit_date", ">=", self.date_from),
            ("tracker_id.visit_date", "<=", self.date_to),
        ]
        if self.user_id:
            checkin_domain.append(("tracker_id.user_id", "=", self.user_id.id))

        orphan_checkins = self.env["salesperson.checkin"].search(
            checkin_domain, order="checkin_time asc, id asc"
        ).filtered(lambda c: c.id not in seen_checkin_ids)

        if self.visit_status != "pending":
            for checkin in orphan_checkins:
                tracker = checkin.tracker_id
                plan = tracker.plan_id
                visited_line = self.env["salesperson.tracker.visited.line"].search([
                    ("checkin_id", "=", checkin.id),
                ], limit=1)
                rating = int(visited_line.rating or 0) if visited_line else 0
                rows.append({
                    "plan": plan,
                    "tracker": tracker,
                    "checkin": checkin,
                    "visited_line": visited_line,
                    "visit_date": tracker.visit_date,
                    "user": tracker.user_id,
                    "purpose": tracker.purpose,
                    "visit_plan_ref": plan.name if plan else (tracker.name or ""),
                    "status": "completed" if checkin.state == "checked_out" else "in_progress",
                    "status_label": "Completed" if checkin.state == "checked_out" else "In Progress",
                    "rating": rating,
                })

        # 3) Legacy tracker target rows without a plan/check-in.
        trackers = self._get_relevant_trackers()
        if self.visit_status != "completed":
            for tracker in trackers:
                if tracker.plan_id and tracker.plan_id.id in seen_plan_ids:
                    continue
                has_customer_checkin = self.env["salesperson.checkin"].search_count([
                    ("tracker_id", "=", tracker.id),
                    ("partner_id", "=", partner.id),
                ])
                planned_for_customer = partner in tracker.target_line_ids.mapped("customer_ids")
                if planned_for_customer and not has_customer_checkin:
                    rows.append({
                        "plan": tracker.plan_id,
                        "tracker": tracker,
                        "checkin": False,
                        "visited_line": False,
                        "visit_date": tracker.visit_date,
                        "user": tracker.user_id,
                        "purpose": tracker.purpose,
                        "visit_plan_ref": tracker.plan_id.name if tracker.plan_id else (tracker.name or ""),
                        "status": "pending",
                        "status_label": "Planned / Pending",
                        "rating": 0,
                    })

        rows.sort(key=lambda r: (r["visit_date"] or date.min, r["checkin"].checkin_time if r["checkin"] else fields.Datetime.from_string("1970-01-01 00:00:00")))
        relevant_trackers = self.env["salesperson.tracker"].browse(
            list({r["tracker"].id for r in rows if r["tracker"]})
        )
        return rows, relevant_trackers

    def action_generate_report(self):
        self.ensure_one()
        if not self.partner_id:
            raise ValidationError(_("Please select a Customer before generating the report."))
        self._check_date_range()
        self.line_ids.unlink()

        rows, trackers = self._prepare_report_rows()
        commands = []
        completed = 0
        pending = 0
        visit_minutes = 0.0
        ratings = []

        for row in rows:
            tracker = row["tracker"]
            checkin = row["checkin"]
            if row["status"] == "completed":
                completed += 1
            elif row["status"] == "pending":
                pending += 1

            if checkin:
                visit_minutes += checkin.duration_minutes or 0.0
            if row["rating"]:
                ratings.append(row["rating"])

            commands.append((0, 0, {
                "tracker_id": tracker.id if tracker else False,
                "checkin_id": checkin.id if checkin else False,
                "visit_date": row["visit_date"],
                "visit_plan_ref": row["visit_plan_ref"],
                "user_id": row["user"].id if row["user"] else False,
                "purpose": row["purpose"],
                "checkin_time": checkin.checkin_time if checkin else False,
                "checkout_time": checkin.checkout_time if checkin else False,
                "duration_minutes": checkin.duration_minutes if checkin else 0.0,
                "distance_km": tracker.total_distance_km if tracker else 0.0,
                "status": row["status"],
                "outcome": checkin.meeting_outcome if checkin else False,
                "rating": str(row["rating"]) if row["rating"] else False,
                "notes": checkin.notes if checkin else False,
            }))

        # Distance and expense are tracker-level measurements. Sum each tracker
        # once so repeated customer check-ins do not inflate the report totals.
        tracker_ids_in_rows = {row["tracker"].id for row in rows if row["tracker"]}
        summary_trackers = trackers.filtered(lambda t: t.id in tracker_ids_in_rows)
        total_distance = sum(summary_trackers.mapped("total_distance_km"))
        total_expense = sum(summary_trackers.mapped("actual_total_cost"))

        self.write({
            "line_ids": commands,
            "total_visits": len(rows),
            "completed_visits": completed,
            "pending_visits": pending,
            "total_distance_km": total_distance,
            "total_visit_minutes": visit_minutes,
            "total_expense": total_expense,
            "average_rating": (sum(ratings) / len(ratings)) if ratings else 0.0,
        })

        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Detailed Report"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_reset(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        self.write({
            "user_id": False,
            "date_from": today.replace(day=1),
            "date_to": today,
            "visit_status": "all",
            "line_ids": [(5, 0, 0)],
            "total_visits": 0,
            "completed_visits": 0,
            "pending_visits": 0,
            "total_distance_km": 0.0,
            "total_visit_minutes": 0.0,
            "total_expense": 0.0,
            "average_rating": 0.0,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("Customer Detailed Report"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.partner_id:
            raise ValidationError(_("Please select a Customer before printing the report."))
        if not self.line_ids:
            self.action_generate_report()
        return self.env.ref(
            "zencore_salesperson_tracking.action_report_customer_detailed"
        ).report_action(self)


class SalespersonCustomerReportLine(models.TransientModel):
    _name = "salesperson.customer.report.line"
    _description = "Customer Detailed Report Preview Line"
    _order = "visit_date asc, id asc"

    wizard_id = fields.Many2one(
        "salesperson.customer.report.wizard",
        required=True,
        ondelete="cascade",
    )
    tracker_id = fields.Many2one("salesperson.tracker", string="Tracker", readonly=True)
    checkin_id = fields.Many2one("salesperson.checkin", string="Check-In", readonly=True)
    visit_date = fields.Date(string="Visit Date", readonly=True)
    visit_plan_ref = fields.Char(string="Visit Plan", readonly=True)
    user_id = fields.Many2one("res.users", string="Salesperson", readonly=True)
    purpose = fields.Selection(
        [
            ("order", "New Order"),
            ("payment", "Payment Collection"),
            ("complaint", "Complaint Resolution"),
            ("followup", "Follow Up"),
            ("demo", "Product Demo"),
        ],
        string="Purpose",
        readonly=True,
    )
    checkin_time = fields.Datetime(string="Check In", readonly=True)
    checkout_time = fields.Datetime(string="Check Out", readonly=True)
    duration_minutes = fields.Float(string="Duration (Min)", readonly=True)
    distance_km = fields.Float(string="Distance (KM)", readonly=True)
    status = fields.Selection(
        [
            ("completed", "Completed"),
            ("in_progress", "In Progress"),
            ("pending", "Planned / Pending"),
        ],
        string="Status",
        readonly=True,
    )
    outcome = fields.Selection(
        [
            ("positive", "Positive"),
            ("neutral", "Neutral"),
            ("negative", "Negative"),
            ("followup", "Follow-up Needed"),
            ("deal_closed", "Deal Closed"),
        ],
        string="Outcome",
        readonly=True,
    )
    rating = fields.Selection(
        [
            ("1", "★"),
            ("2", "★★"),
            ("3", "★★★"),
            ("4", "★★★★"),
            ("5", "★★★★★"),
        ],
        string="Rating",
        readonly=True,
    )
    notes = fields.Text(string="Notes", readonly=True)
