import json
import csv
import io
import base64
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SalespersonLocationBackup(models.Model):
    _name = "salesperson.location.backup"
    _description = "Location History Backup"
    _order = "backup_date desc"

    tracker_id = fields.Many2one("salesperson.tracker", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", related="tracker_id.user_id", store=True)

    backup_date = fields.Date(string="Backup Date", required=True)
    record_count = fields.Integer(string="Number of Records")
    payload = fields.Text(string="JSON Data")

    created_at = fields.Datetime(string="Backed Up At", default=fields.Datetime.now)
    expires_at = fields.Datetime(string="Expires At")

    @api.model
    def _get_keep_days(self):
        """Get number of days to keep in live table."""
        return int(self.env["ir.config_parameter"].sudo().get_param(
            "zencore_salesperson_tracking.keep_days", "7"
        ))

    @api.model
    def _get_backup_retention_days(self):
        """Get number of days to keep backups."""
        return int(self.env["ir.config_parameter"].sudo().get_param(
            "zencore_salesperson_tracking.backup_retention_days", "14"
        ))

    @api.model
    def action_run_backup_policy(self):
        """Scheduled action: backup old logs and delete expired backups."""
        self._backup_old_logs()
        self._delete_expired_backups()

    def _backup_old_logs(self):
        LocationLog = self.env["salesperson.location.log"]
        keep_days = self._get_keep_days()
        
        # Backup logs older than keep_days
        cutoff = fields.Datetime.now() - timedelta(days=keep_days)

        old_logs = LocationLog.search([("tracked_at", "<=", cutoff)])

        if not old_logs:
            _logger.info("No location logs older than %d days to backup.", keep_days)
            return

        # Group by tracker and date
        grouped = {}
        for log in old_logs:
            day = log.tracked_at.date()
            key = (log.tracker_id.id, day)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(log)

        backup_vals = []
        for (tracker_id, day), logs in grouped.items():
            records_data = [
                {
                    "tracked_at": log.tracked_at.isoformat(),
                    "latitude": log.latitude,
                    "longitude": log.longitude,
                    "accuracy": log.accuracy,
                    "speed": log.speed,
                    "heading": log.heading,
                    "source": log.source,
                    "location_name": log.location_name,
                }
                for log in logs
            ]
            backup_vals.append({
                "tracker_id": tracker_id,
                "backup_date": day,
                "record_count": len(records_data),
                "payload": json.dumps(records_data),
            })

        if backup_vals:
            self.create(backup_vals)
            old_logs.unlink()
            _logger.info("Backed up %d location logs across %d groups", len(old_logs), len(grouped))

    def _delete_expired_backups(self):
        backup_retention_days = self._get_backup_retention_days()
        
        expired = self.search([
            ("created_at", "<=", fields.Datetime.now() - timedelta(days=backup_retention_days))
        ])
        if expired:
            count = len(expired)
            expired.unlink()
            _logger.info("Deleted %d expired backups (older than %d days)", count, backup_retention_days)

    def action_download_csv(self):
        """Download backup as CSV file."""
        self.ensure_one()
        if not self.payload:
            return

        records = json.loads(self.payload)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            "tracked_at", "latitude", "longitude", "accuracy", "speed", "heading", "source", "location_name"
        ])
        writer.writeheader()
        for rec in records:
            writer.writerow({
                "tracked_at": rec.get("tracked_at", ""),
                "latitude": rec.get("latitude", ""),
                "longitude": rec.get("longitude", ""),
                "accuracy": rec.get("accuracy", ""),
                "speed": rec.get("speed", ""),
                "heading": rec.get("heading", ""),
                "source": rec.get("source", ""),
                "location_name": rec.get("location_name", ""),
            })

        csv_bytes = output.getvalue().encode("utf-8")
        b64 = base64.b64encode(csv_bytes).decode("utf-8")
        filename = f"location_backup_{self.tracker_id.user_id.name}_{self.backup_date}.csv"

        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": b64,
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "text/csv",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }