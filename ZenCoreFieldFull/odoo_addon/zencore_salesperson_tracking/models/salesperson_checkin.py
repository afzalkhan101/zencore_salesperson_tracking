from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

class SalespersonCheckin(models.Model):
    _name = "salesperson.checkin"
    _description = "Customer Check-In Record"
    _order = "checkin_time desc"

    name = fields.Char(string="Reference", compute="_compute_name", store=True)
    tracker_id = fields.Many2one("salesperson.tracker", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", related="tracker_id.user_id", store=True)

    partner_id = fields.Many2one("res.partner", string="Customer", required=True)
    target_line_id = fields.Many2one("salesperson.visit.plan.line", string="Target Line")

    location_name = fields.Char(string="Location")
    checkin_time = fields.Datetime(string="Check-In Time", required=True, default=fields.Datetime.now)
    checkout_time = fields.Datetime(string="Check-Out Time")

    checkin_latitude = fields.Float(string="Check-In Latitude", digits=(16, 7))
    checkin_longitude = fields.Float(string="Check-In Longitude", digits=(16, 7))
    checkout_latitude = fields.Float(string="Check-Out Latitude", digits=(16, 7))
    checkout_longitude = fields.Float(string="Check-Out Longitude", digits=(16, 7))

    duration_minutes = fields.Float(string="Duration (min)", compute="_compute_duration", store=True)

    state = fields.Selection([
        ("checked_in", "Checked In"),
        ("checked_out", "Checked Out"),
    ], default="checked_in")

    # Selfie
    selfie_image = fields.Binary(string="Selfie", attachment=True)
    selfie_filename = fields.Char(string="Selfie Filename")
    selfie_latitude = fields.Float(string="Selfie Latitude", digits=(16, 7))
    selfie_longitude = fields.Float(string="Selfie Longitude", digits=(16, 7))
    selfie_taken_at = fields.Datetime(string="Selfie Taken At")

    # Meeting outcome
    notes = fields.Text(string="Notes")
    meeting_outcome = fields.Selection([
        ("positive", "Positive"),
        ("neutral", "Neutral"),
        ("negative", "Negative"),
        ("followup", "Follow-up Needed"),
        ("deal_closed", "Deal Closed"),
    ], string="Meeting Outcome")
    customer_feedback = fields.Text(string="Customer Feedback")

    @api.depends("checkin_time", "checkout_time")
    def _compute_name(self):
        for checkin in self:
            checkin.name = f"{checkin.user_id.name} - {checkin.partner_id.name}" if checkin.user_id and checkin.partner_id else "New"

    @api.depends("checkin_time", "checkout_time")
    def _compute_duration(self):
        for checkin in self:
            if checkin.checkin_time and checkin.checkout_time:
                delta = checkin.checkout_time - checkin.checkin_time
                checkin.duration_minutes = delta.total_seconds() / 60.0
            else:
                checkin.duration_minutes = 0.0

    def action_checkout(self, latitude=None, longitude=None):
        self.ensure_one()
        if self.state == "checked_out":
            return

        checkout_time = fields.Datetime.now()
        vals = {
            "checkout_time": checkout_time,
            "state": "checked_out",
        }
        if latitude:
            vals["checkout_latitude"] = latitude
        if longitude:
            vals["checkout_longitude"] = longitude
        self.write(vals)

        # Create visited line in tracker (only if not already exists)
        existing_visited = self.env["salesperson.tracker.visited.line"].sudo().search([
            ("checkin_id", "=", self.id),
        ], limit=1)
        
        if not existing_visited:
            visited_line = self.env["salesperson.tracker.visited.line"].create({
                "tracker_id": self.tracker_id.id,
                "checkin_id": self.id,
                "partner_id": self.partner_id.id,
                "checkin_time": self.checkin_time,
                "checkout_time": checkout_time,
            })
            _logger.info("action_checkout: created visited_line id=%s for partner=%s", 
                        visited_line.id, self.partner_id.name)
        else:
            # Update existing visited line with checkout time if missing
            if not existing_visited.checkout_time:
                existing_visited.write({"checkout_time": checkout_time})
            visited_line = existing_visited
        
        # Update tracker counts
        if self.tracker_id:
            self.tracker_id._compute_counts()
            # Update total visit time
            if visited_line.time_spent_minutes:
                self.tracker_id.total_visit_time_minutes += visited_line.time_spent_minutes

        # Mark target line as visited
        if self.target_line_id:
            self.target_line_id.mark_visited(self.checkin_time, checkout_time)
        
        _logger.info("action_checkout: completed for checkin=%s partner=%s", 
                    self.id, self.partner_id.name)