from odoo import api, fields, models


class SalespersonVisitPlanLine(models.Model):
    _name = "salesperson.visit.plan.line"
    _description = "Visit Plan Target Line"
    _order = "sequence, id"

    plan_id = fields.Many2one("salesperson.visit.plan", string="Visit Plan", required=True, ondelete="cascade")
    sequence = fields.Integer(string="Sequence", default=10)

    expected_time_minutes = fields.Integer(string="Expected Time (minutes)")
    employee_ids = fields.Many2many("hr.employee", string="Accompanies")

    # Route Info
    from_location = fields.Char(string="From Location")
    from_latitude = fields.Float(string="From Latitude", digits=(10, 7))
    from_longitude = fields.Float(string="From Longitude", digits=(10, 7))
    # Filled automatically from the selected customer. Kept for historic route
    # compatibility, but never entered or shown as a separate form field.
    to_location = fields.Char(string="To Location")
    expected_km = fields.Float(string="Expected KM", digits=(16, 2))


    customer_ids = fields.Many2many(
        "res.partner",
        string="Customers",
        domain="[('active', '=', True), ('customer_rank', '>', 0), ('user_ids', '=', False)]",
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

    def mark_visited(self, checkin_time, checkout_time, tracker=None):
        """Update the line summary without completing a multi-customer line early.

        The tracker stores one visited line per customer, which is the source
        of truth for each customer's In/Exit time.  This plan-line summary can
        only become completed when every customer assigned to the line has an
        individual checkout.
        """
        self.ensure_one()
        if tracker and self.customer_ids:
            completed_visits = self.env['salesperson.tracker.visited.line'].sudo().search([
                ('tracker_id', '=', tracker.id),
                ('partner_id', 'in', self.customer_ids.ids),
                ('checkout_time', '!=', False),
            ], order='checkin_time asc')
            completed_partner_ids = set(completed_visits.mapped('partner_id').ids)
            if not set(self.customer_ids.ids).issubset(completed_partner_ids):
                # Leave aggregate completion false: individual customers still
                # appear in the tracker Visited Lines tab with their own times.
                self.write({'is_visited': False})
                return
            checkin_time = min(completed_visits.mapped('checkin_time'))
            checkout_time = max(completed_visits.mapped('checkout_time'))

        duration = 0
        if checkout_time and checkin_time:
            duration = (checkout_time - checkin_time).total_seconds() / 60.0
        self.write({
            "is_visited": True,
            "actual_checkin_time": checkin_time,
            "actual_checkout_time": checkout_time,
            "actual_duration_minutes": duration,
        })
