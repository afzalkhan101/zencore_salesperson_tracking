from odoo import fields, models, api


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    location_keep_days = fields.Integer(
        string="Keep Location Data (days)",
        config_parameter="zencore_salesperson_tracking.keep_days",
        default=7,
        help="Number of days to keep recent location data. Older data will be backed up."
    )

    backup_retention_days = fields.Integer(
        string="Backup Retention (days)",
        config_parameter="zencore_salesperson_tracking.backup_retention_days",
        default=14,
        help="Number of days to keep backups. Backups older than this will be auto-deleted."
    )

    geofence_radius_meters = fields.Integer(
        string="Geofence Radius (meters)",
        config_parameter="zencore_salesperson_tracking.geofence_radius",
        default=100,
        help="Radius in meters for auto check-in/out detection"
    )

    @api.model
    def _get_param(self, key, default=None):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    def set_values(self):
        super().set_values()
        for record in self:
            record.env["ir.config_parameter"].sudo().set_param(
                "zencore_salesperson_tracking.geofence_radius",
                record.geofence_radius_meters
            )
            # NOTE: there is no in-memory "live" copy of this value to
            # update — salesperson.tracker._get_geofence_radius() always
            # reads straight from ir.config_parameter (set just above) on
            # every call, so the new radius takes effect immediately for
            # all subsequent geofence checks. There used to be a stray
            # line here trying to set a GEOFENCE_RADIUS_METERS class
            # attribute that doesn't exist on the model — that's what was
            # throwing the AttributeError on Save.

    def get_values(self):
        res = super().get_values()
        res.update(
            geofence_radius_meters=int(self.env["ir.config_parameter"].sudo().get_param(
                "zencore_salesperson_tracking.geofence_radius", "100"))
        )
        return res