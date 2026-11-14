from odoo import api, fields, models, _


class SalespersonTrackingSession(models.Model):
    _name = "salesperson.tracking.session"
    _description = "Tracking Session (each online/offline cycle)"
    _order = "start_time desc"

    tracker_id = fields.Many2one("salesperson.tracker", required=True, ondelete="cascade")
    start_time = fields.Datetime(string="Session Start", required=True, default=fields.Datetime.now)
    end_time = fields.Datetime(string="Session End")
    duration_seconds = fields.Integer(string="Duration (seconds)", compute="_compute_duration", store=True)
    duration_display = fields.Char(string="Duration", compute="_compute_duration", store=True)

    last_location_lat = fields.Float(string="Last Latitude", digits=(16, 7))
    last_location_lng = fields.Float(string="Last Longitude", digits=(16, 7))

    state = fields.Selection([
        ("active", "Active"),
        ("stopped", "Stopped"),
    ], default="active")

    @api.depends("start_time", "end_time")
    def _compute_duration(self):
        for session in self:
            if session.end_time and session.start_time:
                seconds = (session.end_time - session.start_time).total_seconds()
                session.duration_seconds = int(seconds)
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = int(seconds % 60)
                session.duration_display = f"{hours:02d}:{minutes:02d}:{secs:02d}"
            else:
                session.duration_seconds = 0
                session.duration_display = "00:00:00"

    def action_stop(self):
        self.ensure_one()
        self.write({
            "end_time": fields.Datetime.now(),
            "state": "stopped",
        })

        # Update tracker's total tracking time
        tracker = self.tracker_id
        tracker.total_tracking_time_seconds += self.duration_seconds