from odoo import api, fields, models


class SalespersonVisitPlanLineTravel(models.Model):
    """Persist the route decision made in the mobile plan editor.

    The route is deliberately stored on the target line.  A plan can contain
    multiple customer routes and each can use a different transport mode.
    Actual costs remain on the tracker as auditable expense entries instead of
    being guessed or split across customer lines.
    """

    _inherit = "salesperson.visit.plan.line"

    travel_mode = fields.Selection(
        [("walk", "Walk"), ("bike", "Bike"), ("car", "Car")],
        string="Travel Mode",
        default="car",
        required=True,
    )
    planned_duration_minutes = fields.Integer(
        string="Planned Travel Time (min)", default=0,
        help="Estimated travel time returned by the route selected in the mobile app.",
    )


class SalespersonTrackerTargetLineTravel(models.Model):
    """Expose the planned route on the tracking record without duplicating it."""

    _inherit = "salesperson.tracker.target.line"

    travel_mode = fields.Selection(
        related="plan_line_id.travel_mode", string="Travel Mode", readonly=True
    )
    planned_duration_minutes = fields.Integer(
        related="plan_line_id.planned_duration_minutes", string="ETA (min)", readonly=True
    )


class SalespersonVisitPlanTravelSummary(models.Model):
    """Read-only plan summary for the backend form and printed plan report."""

    _inherit = "salesperson.visit.plan"

    planned_distance_km = fields.Float(
        string="Planned Distance (KM)", compute="_compute_travel_cost_summary"
    )
    planned_travel_minutes = fields.Integer(
        string="Planned Travel Time (min)", compute="_compute_travel_cost_summary"
    )
    actual_distance_km = fields.Float(
        string="Actual GPS Distance (KM)", compute="_compute_travel_cost_summary"
    )
    actual_travel_minutes = fields.Float(
        string="Actual Travel Time (min)", compute="_compute_travel_cost_summary"
    )
    actual_expense_total = fields.Float(
        string="Actual Expense", compute="_compute_travel_cost_summary"
    )
    expense_balance = fields.Float(
        string="Expense Balance", compute="_compute_travel_cost_summary",
        help="Claimed total minus actual logged expense. A negative value means over budget.",
    )
    tracker_ids = fields.One2many(
        "salesperson.tracker", "plan_id", string="Tracking Records"
    )

    @api.depends(
        "target_line_ids.expected_km",
        "target_line_ids.planned_duration_minutes",
        "transport_cost",
        "food_cost",
        "other_cost",
        "tracker_ids.total_distance_km",
        "tracker_ids.traveling_time_minutes",
        "tracker_ids.actual_total_cost",
    )
    def _compute_travel_cost_summary(self):
        trackers_by_plan = {}
        if self.ids:
            trackers = self.env["salesperson.tracker"].sudo().search(
                [("plan_id", "in", self.ids)], order="id desc"
            )
            for tracker in trackers:
                # A plan has a single tracker in normal operation.  Keep the
                # most recent one as a safe fallback for historical records.
                trackers_by_plan.setdefault(tracker.plan_id.id, tracker)
        for plan in self:
            tracker = trackers_by_plan.get(plan.id)
            plan.planned_distance_km = sum(plan.target_line_ids.mapped("expected_km"))
            plan.planned_travel_minutes = sum(plan.target_line_ids.mapped("planned_duration_minutes"))
            plan.actual_distance_km = tracker.total_distance_km if tracker else 0.0
            plan.actual_travel_minutes = tracker.traveling_time_minutes if tracker else 0.0
            plan.actual_expense_total = tracker.actual_total_cost if tracker else 0.0
            plan.expense_balance = plan.total_cost - plan.actual_expense_total
