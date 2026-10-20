from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SalespersonLocationLog(models.Model):
    _name = "salesperson.location.log"
    _description = "Location History (every 2 seconds)"
    _order = "tracked_at desc"
    _auto_manage = True

    tracker_id = fields.Many2one("salesperson.tracker", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", related="tracker_id.user_id", store=True, index=True)

    tracked_at = fields.Datetime(string="Timestamp", required=True, default=fields.Datetime.now, index=True)
    latitude = fields.Float(string="Latitude", digits=(16, 7), default=0.0)
    longitude = fields.Float(string="Longitude", digits=(16, 7), default=0.0)
    accuracy = fields.Float(string="Accuracy (m)", digits=(16, 2))
    speed = fields.Float(string="Speed (m/s)", digits=(16, 2))
    heading = fields.Float(string="Heading", digits=(16, 2))
    source = fields.Char(string="Source", default="browser")
    location_name = fields.Char(string="Location Name")
    
    # Photo fields
    photo = fields.Binary(string="Photo", attachment=True)
    photo_filename = fields.Char(string="Photo Filename")
    photo_taken_at = fields.Datetime(string="Photo Taken At")

    openstreetmap_url = fields.Char(compute="_compute_map_url")

    @api.depends("latitude", "longitude")
    def _compute_map_url(self):
        
        existing = self.exists()
        missing = self - existing
        if missing:
            missing.openstreetmap_url = False
        for log in existing:
            if log.latitude and log.longitude:
                log.openstreetmap_url = (
                    f"https://www.openstreetmap.org/?mlat={log.latitude}"
                    f"&mlon={log.longitude}#map=16/{log.latitude}/{log.longitude}"
                )
            else:
                log.openstreetmap_url = False
    
    def action_download_photo(self):
        self.ensure_one()
        if not self.photo:
            raise ValidationError(_("No photo attached to this log entry."))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/salesperson.location.log/{self.id}/photo/{self.photo_filename or "photo.jpg"}?download=true',
            'target': 'self',
        }