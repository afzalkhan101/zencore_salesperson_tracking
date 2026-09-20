from odoo import api, fields, models


class SalespersonVisitPlanLine(models.Model):
    _name = "salesperson.visit.plan.line"
    _description = "Visit Plan Target Line"
    _order = "sequence, id"

    plan_id = fields.Many2one("salesperson.visit.plan", string="Visit Plan", required=True, ondelete="cascade")
    sequence = fields.Integer(string="Sequence", default=10)

    # Basic Info
    expected_time_minutes = fields.Integer(string="Expected Time (minutes)")
    employee_ids = fields.Many2many("hr.employee", string="Accompanies")

    # Route Info
    from_location = fields.Char(string="From Location")
    to_location = fields.Char(string="To Location")
    expected_km = fields.Float(string="Expected KM", digits=(16, 2))

    # Customers - MANY2MANY
    customer_ids = fields.Many2many(
        "res.partner",
        string="Customers",
        domain=[("customer_rank", ">", 0)],
        help="Customers to visit in this line"
    )
    customer_count = fields.Integer(compute="_compute_customer_count", store=True)

    # Tracking fields
    actual_checkin_time = fields.Datetime(string="Actual Check-In")
    actual_checkout_time = fields.Datetime(string="Actual Check-Out")
    is_visited = fields.Boolean(string="Visited", default=False)
    actual_duration_minutes = fields.Float(string="Actual Duration (min)")

    # Notes
    notes = fields.Text(string="Notes")

    @api.depends("customer_ids")
    def _compute_customer_count(self):
        for line in self:
            line.customer_count = len(line.customer_ids)

    def mark_visited(self, checkin_time, checkout_time):
        self.ensure_one()
        duration = 0
        if checkout_time and checkin_time:
            duration = (checkout_time - checkin_time).total_seconds() / 60.0
        self.write({
            "is_visited": True,
            "actual_checkin_time": checkin_time,
            "actual_checkout_time": checkout_time,
            "actual_duration_minutes": duration,
        })