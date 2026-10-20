import base64
import logging
from datetime import datetime
from odoo import http, fields, _
from odoo.http import request
from markupsafe import Markup

_logger = logging.getLogger(__name__)


class SalespersonTrackingController(http.Controller):

    @http.route("/salesperson_tracking/save_photo", type="json", auth="user", methods=["POST"], csrf=False)
    def save_photo(self, **kwargs):
        """Save photo from camera"""
        try:
            _logger.info("save_photo: received request with keys: %s", kwargs.keys())
            
            image_data = kwargs.get('image_data', '')
            filename = kwargs.get('filename', '')
            latitude = kwargs.get('latitude')
            longitude = kwargs.get('longitude')
            location_name = kwargs.get('location_name', '')
            
            if not image_data:
                _logger.error("save_photo: No image data received")
                return {"success": False, "error": "No image data received"}

            if not filename:
                filename = f"photo_{request.env.user.id}_{int(datetime.now().timestamp())}.jpg"

            if ',' in image_data:
                image_b64 = image_data.split(',', 1)[1]
            else:
                image_b64 = image_data

            _logger.info("save_photo: image data length: %d chars", len(image_b64))
            tracker = request.env["salesperson.tracker"].sudo().search(
                [("user_id", "=", request.env.uid)], limit=1
            )
            if not tracker:
                tracker = request.env["salesperson.tracker"].sudo().create({
                    "user_id": request.env.uid,
                    "visit_date": fields.Date.today(),
                    "state": "planned",
                })
                _logger.info("save_photo: created new tracker id=%s", tracker.id)
            taken_at = fields.Datetime.now()
            
            attachment = request.env["ir.attachment"].sudo().create({
                "name": filename,
                "type": "binary",
                "datas": image_b64,
                "mimetype": "image/jpeg",
                "res_model": "salesperson.tracker",
                "res_id": tracker.id,
            })
            _logger.info("save_photo: created attachment id=%s", attachment.id)

            # Create location log with photo
            location_log_vals = {
                "tracker_id": tracker.id,
                "user_id": request.env.uid,
                "tracked_at": taken_at,
                "source": "camera",
                "photo": image_b64,
                "photo_filename": filename,
                "photo_taken_at": taken_at,
            }
            
            # Add coordinates if provided
            if latitude and longitude:
                try:
                    location_log_vals["latitude"] = float(latitude)
                    location_log_vals["longitude"] = float(longitude)
                    location_log_vals["location_name"] = location_name or ""
                except (TypeError, ValueError):
                    _logger.warning("save_photo: invalid coordinates - lat=%s, lng=%s", latitude, longitude)
            
            location_log = request.env["salesperson.location.log"].sudo().create(location_log_vals)
            _logger.info("save_photo: created location_log id=%s", location_log.id)

            # Post message to chatter
            location_info = ""
            if latitude and longitude:
                maps_url = f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=16/{latitude}/{longitude}"
                place_label = location_name or f"{latitude}, {longitude}"
                location_info = f'<br/><b>Location:</b> <a href="{maps_url}" target="_blank">{place_label}</a>'

            tracker.message_post(
                body=Markup(
                    f"<b>📸 Photo uploaded</b> by {request.env.user.name}<br/>"
                    f"<b>Taken at:</b> {taken_at.strftime('%Y-%m-%d %H:%M:%S')}{location_info}"
                ),
                attachment_ids=[attachment.id],
            )

            # Attach to active check-in if exists
            active_checkin = request.env["salesperson.checkin"].sudo().search([
                ("tracker_id", "=", tracker.id),
                ("state", "=", "checked_in"),
            ], limit=1)
            if active_checkin:
                active_checkin.write({
                    "selfie_image": image_b64,
                    "selfie_filename": filename,
                    "selfie_latitude": latitude or 0.0,
                    "selfie_longitude": longitude or 0.0,
                    "selfie_taken_at": taken_at,
                })
                _logger.info("save_photo: attached to checkin id=%s", active_checkin.id)

            return {
                "success": True,
                "attachment_id": attachment.id,
                "location_log_id": location_log.id,
                "message": "Photo saved successfully",
            }

        except Exception as e:
            _logger.error("save_photo error: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}