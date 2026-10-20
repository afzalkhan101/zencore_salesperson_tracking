import json
import base64
import logging
from odoo import fields, http, _
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)


class MobileApiController(http.Controller):

    def _json_response(self, data):
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
        )

    def _json_body(self):
        payload = request.httprequest.data or b'{}'
        return json.loads(payload.decode('utf-8'))

    def _require_user(self):
        user = request.env.user
        if user._is_public():
            raise AccessError('Login required')
        return user

    def _is_manager(self, user):
        return getattr(user, 'salesperson_role', '') == 'manager'

    def _tracker_accessible(self, tracker, user):
        """Salesman can only access own trackers; manager can access all."""
        if self._is_manager(user):
            return True
        return tracker.user_id.id == user.id

    # ── Visit Plans ───────────────────────────────────────────────────────────

    @http.route('/mobile/api/plans', type='http', auth='user', csrf=False, methods=['GET'])
    def get_plans(self, **kwargs):
        """Return all plans for current user (all dates, all states)."""
        try:
            user = self._require_user()
            is_manager = getattr(user, 'salesperson_role', '') == 'manager'

            domain = []
            if not is_manager:
                domain = [('user_id', '=', user.id)]

            plans = request.env['salesperson.visit.plan'].sudo().search(
                domain, order='visit_date desc', limit=50
            )

            PURPOSE_LABELS = {
                'order': 'New Order', 'payment': 'Payment Collection',
                'complaint': 'Complaint Resolution', 'followup': 'Follow Up',
                'demo': 'Product Demo',
            }
            STATE_LABELS = {
                'draft': 'Draft', 'submitted': 'Submitted', 'approved': 'Approved',
                'rejected': 'Rejected', 'in_progress': 'In Progress', 'completed': 'Completed',
            }

            result = []
            for p in plans:
                result.append({
                    'id': p.id,
                    'name': p.name,
                    'visit_date': str(p.visit_date),
                    'salesman': p.user_id.name,
                    'salesman_id': p.user_id.id,
                    'purpose': p.purpose,
                    'purpose_label': PURPOSE_LABELS.get(p.purpose, p.purpose),
                    'state': p.state,
                    'state_label': STATE_LABELS.get(p.state, p.state),
                    'total_visits': p.total_visits,
                })

            return self._json_response({'ok': True, 'plans': result})
        except Exception as e:
            _logger.error('get_plans error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    @http.route('/mobile/api/plans/create', type='http', auth='user', csrf=False, methods=['POST'])
    def create_plan(self, **kwargs):
        """Create a visit plan from mobile. State = submitted (needs approval)."""
        try:
            user = self._require_user()
            body = self._json_body()

            visit_date = body.get('visit_date') or str(fields.Date.today())
            purpose = body.get('purpose', 'followup')
            customer_ids = body.get('customer_ids', [])
            notes = body.get('notes', '')

            if not customer_ids:
                return self._json_response({'ok': False, 'message': 'At least one customer required'})
            
            plan = request.env['salesperson.visit.plan'].sudo().create({
                'user_id': user.id,
                'visit_date': visit_date,
                'purpose': purpose,
                'state': 'draft',
            })

            # Create target line with all customers
            request.env['salesperson.visit.plan.line'].sudo().create({
                'plan_id': plan.id,
                'customer_ids': [(6, 0, customer_ids)],
            })
            # Auto-submit for approval
            plan.action_submit()
            _logger.info('create_plan: user=%s plan=%s date=%s customers=%s',
                         user.name, plan.name, visit_date, customer_ids)
            return self._json_response({
                'ok': True,
                'plan_id': plan.id,
                'plan_name': plan.name,
                'state': plan.state,
            })
        except Exception as e:
            _logger.error('create_plan error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})
        
    @http.route('/mobile/api/plans/<int:plan_id>/approve', type='http', auth='user', csrf=False, methods=['POST'])
    def approve_plan(self, plan_id, **kwargs):
        """Manager approves a submitted plan."""
        try:
            user = self._require_user()
            if getattr(user, 'salesperson_role', '') != 'manager':
                return self._json_response({'ok': False, 'message': 'Only managers can approve plans'})
            plan = request.env['salesperson.visit.plan'].sudo().browse(plan_id)
            if not plan.exists():
                return self._json_response({'ok': False, 'message': 'Plan not found'})

            if plan.state != 'submitted':
                return self._json_response({'ok': False, 'message': f'Plan is {plan.state}, not submitted'})
            plan.action_approve()
            return self._json_response({'ok': True, 'state': plan.state})
        except Exception as e:
            _logger.error('approve_plan error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    @http.route('/mobile/api/plans/<int:plan_id>/customers', type='http', auth='user', csrf=False, methods=['GET'])
    def get_plan_customers(self, plan_id, **kwargs):
        """Return customers in a plan with visited status."""
        try:
            user = self._require_user()
            plan = request.env['salesperson.visit.plan'].sudo().browse(plan_id)
            if not plan.exists():
                return self._json_response({'ok': False, 'message': 'Plan not found'})
            # Get tracker for today to determine visited status
            today = fields.Date.today()
            tracker = request.env['salesperson.tracker'].sudo().search([
                ('user_id', '=', user.id),
                ('visit_date', '=', today),
            ], limit=1, order='id desc')
            visited_ids = set()
            checkin_map = {}
            if tracker:
                visited_ids = {v.partner_id.id for v in tracker.visited_line_ids}
                for v in tracker.visited_line_ids:
                    checkin_map[v.partner_id.id] = {
                        'checkin_time': str(v.checkin_time) if v.checkin_time else '',
                        'checkout_time': str(v.checkout_time) if v.checkout_time else '',
                        'time_spent': v.time_spent_minutes,
                    }

            customers = []
            seen = set()
            for line in plan.target_line_ids:
                for partner in line.customer_ids:
                    if partner.id in seen:
                        continue
                    seen.add(partner.id)
                    info = checkin_map.get(partner.id, {})
                    customers.append({
                        'id': partner.id,
                        'name': partner.name,
                        'street': partner.street or '',
                        'city': partner.city or '',
                        'phone': partner.phone or partner.mobile or '',
                        'latitude': partner.partner_latitude or 0,
                        'longitude': partner.partner_longitude or 0,
                        'visited': partner.id in visited_ids,
                        'checkin_time': info.get('checkin_time', ''),
                        'checkout_time': info.get('checkout_time', ''),
                        'time_spent_minutes': info.get('time_spent', 0),
                    })

            is_tracking = tracker.is_tracking if tracker else False

            return self._json_response({
                'ok': True,
                'customers': customers,
                'tracker_id': tracker.id if tracker else None,
                'is_tracking': is_tracking,
            })
        except Exception as e:
            _logger.error('get_plan_customers error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Partner Search ────────────────────────────────────────────────────────

    @http.route('/mobile/api/partners/search', type='http', auth='user', csrf=False, methods=['GET'])
    def search_partners(self, q='', **kwargs):
        """Search res.partner by name, phone, or email."""
        try:
            self._require_user()
            if len(q) < 2:
                return self._json_response({'ok': True, 'partners': []})

            partners = request.env['res.partner'].sudo().search([
                ('is_company', 'in', [True, False]),
                ('active', '=', True),
                '|', '|',
                ('name', 'ilike', q),
                ('phone', 'ilike', q),
                ('mobile', 'ilike', q),
            ], limit=20)

            result = [{
                'id': p.id,
                'name': p.name,
                'street': p.street or '',
                'city': p.city or '',
                'phone': p.phone or p.mobile or '',
                'email': p.email or '',
                'latitude': p.partner_latitude or 0,
                'longitude': p.partner_longitude or 0,
            } for p in partners]

            return self._json_response({'ok': True, 'partners': result})
        except Exception as e:
            _logger.error('search_partners error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Tracker ───────────────────────────────────────────────────────────────

    @http.route('/mobile/api/tracker/today', type='http', auth='user', csrf=False, methods=['GET'])
    def get_today_tracker(self, **kwargs):
        """Return today's tracker info for current user."""
        try:
            user = self._require_user()
            today = fields.Date.today()

            tracker = request.env['salesperson.tracker'].sudo().search([
                ('user_id', '=', user.id),
                ('visit_date', '=', today),
            ], limit=1, order='id desc')

            if not tracker:
                return self._json_response({'ok': True, 'tracker': None})

            return self._json_response({
                'ok': True,
                'tracker': {
                    'id': tracker.id,
                    'is_tracking': tracker.is_tracking,
                    'plan_id': tracker.plan_id.id if tracker.plan_id else None,
                    'plan_name': tracker.plan_id.name if tracker.plan_id else '',
                    'total_visits': tracker.total_visits,
                    'total_visited': tracker.total_visited,
                    'total_distance_km': round(tracker.total_distance_km or 0, 2),
                    'duration_hours': round(tracker.duration_hours or 0, 2),
                    'state': tracker.state,
                    'last_latitude': tracker.last_latitude or 0,
                    'last_longitude': tracker.last_longitude or 0,
                    'last_accuracy': tracker.last_accuracy or 0,
                    'last_seen': str(tracker.last_seen) if tracker.last_seen else '',
                    'location_name': tracker.location_name or '',
                },
            })
        except Exception as e:
            _logger.error('get_today_tracker error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Check-in / Check-out ──────────────────────────────────────────────────

    @http.route('/mobile/api/checkin', type='http', auth='user', csrf=False, methods=['POST'])
    def mobile_checkin(self, **kwargs):
        """Create a check-in record for a customer."""
        try:
            user = self._require_user()
            body = self._json_body()

            partner_id = body.get('partner_id')
            latitude = float(body.get('latitude') or 0)
            longitude = float(body.get('longitude') or 0)
            selfie_b64 = body.get('selfie')

            if not partner_id:
                return self._json_response({'ok': False, 'message': 'partner_id required'})

            partner = request.env['res.partner'].sudo().browse(int(partner_id))
            if not partner.exists():
                return self._json_response({'ok': False, 'message': 'Customer not found'})

            tracker = user._ensure_salesperson_tracker()

            # Close any open check-ins for this tracker
            open_checkins = request.env['salesperson.checkin'].sudo().search([
                ('tracker_id', '=', tracker.id),
                ('state', '=', 'checked_in'),
            ])
            for ci in open_checkins:
                ci.action_checkout(latitude=latitude, longitude=longitude)

            vals = {
                'tracker_id': tracker.id,
                'partner_id': int(partner_id),
                'checkin_latitude': latitude,
                'checkin_longitude': longitude,
                'checkin_time': fields.Datetime.now(),
                'state': 'checked_in',
            }

            # Selfie
            if selfie_b64:
                vals['selfie_image'] = selfie_b64
                vals['selfie_filename'] = f'checkin_{fields.Datetime.now()}.jpg'
                vals['selfie_latitude'] = latitude
                vals['selfie_longitude'] = longitude
                vals['selfie_taken_at'] = fields.Datetime.now()

            checkin = request.env['salesperson.checkin'].sudo().create(vals)
            tracker.write({'current_checkin_id': checkin.id})

            _logger.info('mobile_checkin: user=%s partner=%s checkin=%s', user.name, partner.name, checkin.id)

            return self._json_response({
                'ok': True,
                'checkin_id': checkin.id,
                'customer_name': partner.name,
                'checkin_time': str(checkin.checkin_time),
            })
        except Exception as e:
            _logger.error('mobile_checkin error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    @http.route('/mobile/api/checkout/<int:checkin_id>', type='http', auth='user', csrf=False, methods=['POST'])
    def mobile_checkout(self, checkin_id, **kwargs):
        """Complete check-out with outcome, notes, selfie."""
        try:
            user = self._require_user()
            body = self._json_body()

            latitude = float(body.get('latitude') or 0)
            longitude = float(body.get('longitude') or 0)
            outcome = body.get('outcome', '')
            notes = body.get('notes', '')
            customer_feedback = body.get('customer_feedback', '')
            selfie_b64 = body.get('selfie')

            checkin = request.env['salesperson.checkin'].sudo().browse(checkin_id)
            if not checkin.exists():
                return self._json_response({'ok': False, 'message': 'Check-in not found'})

            if checkin.state == 'checked_out':
                return self._json_response({'ok': False, 'message': 'Already checked out'})

            # Write outcome + notes before checkout
            update_vals = {
                'meeting_outcome': outcome,
                'notes': notes,
                'customer_feedback': customer_feedback,
            }
            if selfie_b64:
                update_vals['selfie_image'] = selfie_b64
                update_vals['selfie_filename'] = f'checkout_{fields.Datetime.now()}.jpg'

            checkin.write(update_vals)
            checkin.action_checkout(latitude=latitude, longitude=longitude)

            # Clear current_checkin_id from tracker
            if checkin.tracker_id and checkin.tracker_id.current_checkin_id.id == checkin_id:
                checkin.tracker_id.write({'current_checkin_id': False})

            _logger.info('mobile_checkout: checkin=%s outcome=%s', checkin_id, outcome)

            return self._json_response({
                'ok': True,
                'checkout_time': str(checkin.checkout_time),
                'duration_minutes': checkin.duration_minutes,
            })
        except Exception as e:
            _logger.error('mobile_checkout error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Customers (directory) ────────────────────────────────────────────────

    @http.route('/mobile/api/partners/create', type='http', auth='user', csrf=False, methods=['POST'])
    def create_partner(self, **kwargs):
        """Create a customer from mobile."""
        try:
            user = self._require_user()
            body = self._json_body()

            name = (body.get('name') or '').strip()
            if not name:
                return self._json_response({'ok': False, 'message': 'Name is required'})

            vals = {
                'name': name,
                'email': body.get('email') or False,
                'street': body.get('street') or False,
                'city': body.get('city') or False,
                'phone': body.get('phone') or False,
                'customer_rank': 1,
                'company_type': 'person',
            }
            lat = body.get('latitude')
            lng = body.get('longitude')
            if lat not in (None, '', 0) and lng not in (None, '', 0):
                try:
                    vals['partner_latitude'] = float(lat)
                    vals['partner_longitude'] = float(lng)
                except (TypeError, ValueError):
                    pass

            partner = request.env['res.partner'].sudo().create(vals)
            _logger.info('create_partner: user=%s partner=%s', user.name, partner.id)

            return self._json_response({
                'ok': True,
                'partner': {
                    'id': partner.id,
                    'name': partner.name,
                    'street': partner.street or '',
                    'city': partner.city or '',
                    'phone': partner.phone or '',
                    'email': partner.email or '',
                    'latitude': partner.partner_latitude or 0,
                    'longitude': partner.partner_longitude or 0,
                },
            })
        except Exception as e:
            _logger.error('create_partner error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Trackers (Live Tracking) ─────────────────────────────────────────────

    @http.route('/mobile/api/trackers', type='http', auth='user', csrf=False, methods=['GET'])
    def get_trackers(self, salesman_id=None, **kwargs):
        """List trackers. Salesman sees own; manager sees all (optionally filtered)."""
        try:
            user = self._require_user()
            is_manager = self._is_manager(user)

            domain = []
            if not is_manager:
                domain = [('user_id', '=', user.id)]
            elif salesman_id:
                domain = [('user_id', '=', int(salesman_id))]

            trackers = request.env['salesperson.tracker'].sudo().search(
                domain, order='visit_date desc, id desc', limit=60
            )

            result = []
            for t in trackers:
                result.append({
                    'id': t.id,
                    'name': t.name,
                    'salesman': t.user_id.name,
                    'salesman_id': t.user_id.id,
                    'visit_date': str(t.visit_date),
                    'state': t.state,
                    'is_tracking': t.is_tracking,
                    'tracking_status_label': t.tracking_status_label,
                    'total_visits': t.total_visits,
                    'total_visited': t.total_visited,
                    'total_distance_km': round(t.total_distance_km or 0, 2),
                    'duration_hours': round(t.duration_hours or 0, 2),
                    'last_seen': str(t.last_seen) if t.last_seen else '',
                })

            return self._json_response({'ok': True, 'trackers': result})
        except Exception as e:
            _logger.error('get_trackers error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    @http.route('/mobile/api/trackers/<int:tracker_id>', type='http', auth='user', csrf=False, methods=['GET'])
    def get_tracker_detail(self, tracker_id, **kwargs):
        """Full tracker detail: costs, target lines, visited lines."""
        try:
            user = self._require_user()
            tracker = request.env['salesperson.tracker'].sudo().browse(tracker_id)
            if not tracker.exists():
                return self._json_response({'ok': False, 'message': 'Tracker not found'})
            if not self._tracker_accessible(tracker, user):
                return self._json_response({'ok': False, 'message': 'Access denied'})

            target_lines = [{
                'id': tl.id,
                'from_location': tl.from_location or '',
                'to_location': tl.to_location or '',
                'expected_km': tl.expected_km or 0,
                'expected_time_minutes': tl.expected_time_minutes or 0,
                'customers': [{'id': c.id, 'name': c.name} for c in tl.customer_ids],
                'notes': tl.notes or '',
            } for tl in tracker.target_line_ids]

            visited_lines = [{
                'id': vl.id,
                'partner_id': vl.partner_id.id,
                'partner_name': vl.partner_id.name,
                'checkin_time': str(vl.checkin_time) if vl.checkin_time else '',
                'checkout_time': str(vl.checkout_time) if vl.checkout_time else '',
                'time_spent_minutes': round(vl.time_spent_minutes or 0, 1),
                'rating': vl.rating or '',
            } for vl in tracker.visited_line_ids]

            return self._json_response({
                'ok': True,
                'tracker': {
                    'id': tracker.id,
                    'name': tracker.name,
                    'salesman': tracker.user_id.name,
                    'salesman_id': tracker.user_id.id,
                    'visit_date': str(tracker.visit_date),
                    'state': tracker.state,
                    'is_tracking': tracker.is_tracking,
                    'tracking_status_label': tracker.tracking_status_label,
                    'plan_id': tracker.plan_id.id if tracker.plan_id else None,
                    'plan_name': tracker.plan_id.name if tracker.plan_id else '',

                    'total_visits': tracker.total_visits,
                    'total_visited': tracker.total_visited,
                    'skipped_visits': tracker.skipped_visits,

                    'total_distance_km': round(tracker.total_distance_km or 0, 2),
                    'duration_hours': round(tracker.duration_hours or 0, 2),
                    'total_tracking_time_minutes': round(tracker.total_tracking_time_minutes or 0, 1),
                    'total_visit_time_minutes': round(tracker.total_visit_time_minutes or 0, 1),
                    'traveling_time_minutes': round(tracker.traveling_time_minutes or 0, 1),

                    'transport_cost': tracker.transport_cost or 0,
                    'food_cost': tracker.food_cost or 0,
                    'other_cost': tracker.other_cost or 0,
                    'total_cost': tracker.total_cost or 0,

                    'actual_transport_cost': tracker.actual_transport_cost or 0,
                    'actual_food_cost': tracker.actual_food_cost or 0,
                    'actual_other_cost': tracker.actual_other_cost or 0,
                    'actual_total_cost': tracker.actual_total_cost or 0,

                    'checkin_time': str(tracker.checkin_time) if tracker.checkin_time else '',
                    'checkout_time': str(tracker.checkout_time) if tracker.checkout_time else '',

                    'last_latitude': tracker.last_latitude or 0,
                    'last_longitude': tracker.last_longitude or 0,
                    'location_name': tracker.location_name or '',
                    'openstreetmap_url': tracker.openstreetmap_url or '',

                    'target_lines': target_lines,
                    'visited_lines': visited_lines,
                },
            })
        except Exception as e:
            _logger.error('get_tracker_detail error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    @http.route('/mobile/api/trackers/<int:tracker_id>/update_cost', type='http', auth='user', csrf=False, methods=['POST'])
    def update_tracker_actual_cost(self, tracker_id, **kwargs):
        """Update only the Actual Cost fields on a tracker."""
        try:
            user = self._require_user()
            tracker = request.env['salesperson.tracker'].sudo().browse(tracker_id)
            if not tracker.exists():
                return self._json_response({'ok': False, 'message': 'Tracker not found'})
            if not self._tracker_accessible(tracker, user):
                return self._json_response({'ok': False, 'message': 'Access denied'})

            body = self._json_body()
            vals = {}
            for key in ('actual_transport_cost', 'actual_food_cost', 'actual_other_cost'):
                if key in body:
                    try:
                        vals[key] = float(body.get(key) or 0)
                    except (TypeError, ValueError):
                        vals[key] = 0.0

            tracker.write(vals)
            _logger.info('update_tracker_actual_cost: tracker=%s vals=%s', tracker_id, vals)

            return self._json_response({'ok': True, 'actual_total_cost': tracker.actual_total_cost})
        except Exception as e:
            _logger.error('update_tracker_actual_cost error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    @http.route('/mobile/api/visited_line/<int:line_id>/rating', type='http', auth='user', csrf=False, methods=['POST'])
    def update_visited_line_rating(self, line_id, **kwargs):
        """Update rating (1-5) on a visited line."""
        try:
            user = self._require_user()
            line = request.env['salesperson.tracker.visited.line'].sudo().browse(line_id)
            if not line.exists():
                return self._json_response({'ok': False, 'message': 'Visited line not found'})
            if not self._tracker_accessible(line.tracker_id, user):
                return self._json_response({'ok': False, 'message': 'Access denied'})

            body = self._json_body()
            rating = str(body.get('rating') or '')
            if rating not in ('1', '2', '3', '4', '5'):
                return self._json_response({'ok': False, 'message': 'Rating must be 1-5'})

            line.write({'rating': rating})
            _logger.info('update_visited_line_rating: line=%s rating=%s', line_id, rating)

            return self._json_response({'ok': True, 'rating': rating})
        except Exception as e:
            _logger.error('update_visited_line_rating error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Screenshot (Tracking Page) ───────────────────────────────────────────

    @http.route('/mobile/api/screenshot', type='http', auth='user', csrf=False, methods=['POST'])
    def mobile_screenshot(self, **kwargs):
        """Capture a geo-tagged screenshot/photo from the mobile Tracking page.
        Mirrors the backend's save_photo behaviour but as a plain HTTP/JSON
        endpoint so the mobile app can reuse its standard fetch helper.
        """
        try:
            user = self._require_user()
            body = self._json_body()

            image_b64 = body.get('image') or ''
            if not image_b64:
                return self._json_response({'ok': False, 'message': 'No image data received'})
            if ',' in image_b64:
                image_b64 = image_b64.split(',', 1)[1]

            tracker_id = body.get('tracker_id')
            if tracker_id:
                tracker = request.env['salesperson.tracker'].sudo().browse(int(tracker_id))
                if not tracker.exists() or not self._tracker_accessible(tracker, user):
                    return self._json_response({'ok': False, 'message': 'Access denied'})
            else:
                tracker = user._ensure_salesperson_tracker()

            latitude = body.get('latitude')
            longitude = body.get('longitude')
            location_name = body.get('location_name') or ''
            taken_at = fields.Datetime.now()
            filename = f"photo_{user.id}_{int(taken_at.timestamp())}.jpg"

            attachment = request.env['ir.attachment'].sudo().create({
                'name': filename,
                'type': 'binary',
                'datas': image_b64,
                'mimetype': 'image/jpeg',
                'res_model': 'salesperson.tracker',
                'res_id': tracker.id,
            })

            log_vals = {
                'tracker_id': tracker.id,
                'user_id': user.id,
                'tracked_at': taken_at,
                'source': 'mobile_camera',
                'photo': image_b64,
                'photo_filename': filename,
                'photo_taken_at': taken_at,
            }
            if latitude and longitude:
                try:
                    log_vals['latitude'] = float(latitude)
                    log_vals['longitude'] = float(longitude)
                    log_vals['location_name'] = location_name
                except (TypeError, ValueError):
                    pass

            location_log = request.env['salesperson.location.log'].sudo().create(log_vals)

            tracker.sudo().message_post(
                body=f"📸 Photo uploaded from mobile by {user.name} at {taken_at.strftime('%Y-%m-%d %H:%M:%S')}",
                attachment_ids=[attachment.id],
            )

            _logger.info('mobile_screenshot: user=%s tracker=%s log=%s', user.name, tracker.id, location_log.id)

            return self._json_response({
                'ok': True,
                'attachment_id': attachment.id,
                'location_log_id': location_log.id,
                'tracker_id': tracker.id,
            })
        except Exception as e:
            _logger.error('mobile_screenshot error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Location History ─────────────────────────────────────────────────────

    @http.route('/mobile/api/location_history', type='http', auth='user', csrf=False, methods=['GET'])
    def get_location_history(self, tracker_id=None, limit=100, **kwargs):
        """Return location log entries for a tracker."""
        try:
            user = self._require_user()

            if not tracker_id:
                # Default to current user's today tracker
                today = fields.Date.today()
                tracker = request.env['salesperson.tracker'].sudo().search([
                    ('user_id', '=', user.id), ('visit_date', '=', today),
                ], limit=1, order='id desc')
            else:
                tracker = request.env['salesperson.tracker'].sudo().browse(int(tracker_id))

            if not tracker or not tracker.exists():
                return self._json_response({'ok': True, 'logs': [], 'tracker': None})
            if not self._tracker_accessible(tracker, user):
                return self._json_response({'ok': False, 'message': 'Access denied'})

            try:
                limit = min(int(limit), 500)
            except (TypeError, ValueError):
                limit = 100

            logs = request.env['salesperson.location.log'].sudo().search(
                [('tracker_id', '=', tracker.id)], order='tracked_at desc', limit=limit
            )

            result = [{
                'id': log.id,
                'tracked_at': str(log.tracked_at),
                'latitude': log.latitude,
                'longitude': log.longitude,
                'accuracy': log.accuracy,
                'speed': log.speed,
                'source': log.source,
                'location_name': log.location_name or '',
                'has_photo': bool(log.photo),
                'openstreetmap_url': log.openstreetmap_url or '',
            } for log in logs]

            return self._json_response({
                'ok': True,
                'logs': result,
                'tracker': {
                    'id': tracker.id,
                    'salesman': tracker.user_id.name,
                    'visit_date': str(tracker.visit_date),
                },
            })
        except Exception as e:
            _logger.error('get_location_history error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Manager Dashboard ────────────────────────────────────────────────────

    @http.route('/mobile/api/dashboard', type='http', auth='user', csrf=False, methods=['GET'])
    def get_dashboard(self, **kwargs):
        """Manager dashboard: every salesman with today's tracking status."""
        try:
            user = self._require_user()
            if not self._is_manager(user):
                return self._json_response({'ok': False, 'message': 'Managers only'})

            today = fields.Date.today()
            salesmen = request.env['res.users'].sudo().search([
                ('salesperson_role', '=', 'salesman'),
            ], order='name')

            result = []
            for s in salesmen:
                tracker = request.env['salesperson.tracker'].sudo().search([
                    ('user_id', '=', s.id), ('visit_date', '=', today),
                ], limit=1, order='id desc')

                result.append({
                    'user_id': s.id,
                    'name': s.name,
                    'is_tracking': tracker.is_tracking if tracker else False,
                    'tracking_status_label': tracker.tracking_status_label if tracker else 'Offline',
                    'tracker_id': tracker.id if tracker else None,
                    'last_seen': str(tracker.last_seen) if tracker and tracker.last_seen else '',
                    'total_visits': tracker.total_visits if tracker else 0,
                    'total_visited': tracker.total_visited if tracker else 0,
                    'total_distance_km': round(tracker.total_distance_km or 0, 2) if tracker else 0,
                    'location_name': tracker.location_name if tracker else '',
                    'last_latitude': tracker.last_latitude if tracker else 0,
                    'last_longitude': tracker.last_longitude if tracker else 0,
                })

            return self._json_response({'ok': True, 'salesmen': result})
        except Exception as e:
            _logger.error('get_dashboard error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Backups ───────────────────────────────────────────────────────────────

    @http.route('/mobile/api/backups', type='http', auth='user', csrf=False, methods=['GET'])
    def get_backups(self, **kwargs):
        """List location-history backups. Managers see all; salesmen see own."""
        try:
            user = self._require_user()
            domain = [] if self._is_manager(user) else [('user_id', '=', user.id)]

            backups = request.env['salesperson.location.backup'].sudo().search(
                domain, order='backup_date desc', limit=100
            )

            result = [{
                'id': b.id,
                'salesman': b.user_id.name,
                'salesman_id': b.user_id.id,
                'tracker_id': b.tracker_id.id,
                'backup_date': str(b.backup_date),
                'record_count': b.record_count,
                'created_at': str(b.created_at) if b.created_at else '',
            } for b in backups]

            return self._json_response({'ok': True, 'backups': result})
        except Exception as e:
            _logger.error('get_backups error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    @http.route('/mobile/api/backups/<int:backup_id>/csv', type='http', auth='user', csrf=False, methods=['GET'])
    def get_backup_csv(self, backup_id, **kwargs):
        """Return the backup payload as base64-encoded CSV for the app to save/share."""
        try:
            import csv
            import io
            import base64

            user = self._require_user()
            backup = request.env['salesperson.location.backup'].sudo().browse(backup_id)
            if not backup.exists():
                return self._json_response({'ok': False, 'message': 'Backup not found'})
            if not self._is_manager(user) and backup.user_id.id != user.id:
                return self._json_response({'ok': False, 'message': 'Access denied'})

            records = json.loads(backup.payload or '[]')
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=[
                'tracked_at', 'latitude', 'longitude', 'accuracy', 'speed', 'heading', 'source', 'location_name',
            ])
            writer.writeheader()
            for rec in records:
                writer.writerow({k: rec.get(k, '') for k in writer.fieldnames})

            csv_b64 = base64.b64encode(output.getvalue().encode('utf-8')).decode('utf-8')
            filename = f"location_backup_{backup.user_id.name}_{backup.backup_date}.csv"

            return self._json_response({'ok': True, 'filename': filename, 'content_base64': csv_b64})
        except Exception as e:
            _logger.error('get_backup_csv error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Plan Reject (Manager) ────────────────────────────────────────────────

    @http.route('/mobile/api/plans/<int:plan_id>/reject', type='http', auth='user', csrf=False, methods=['POST'])
    def reject_plan(self, plan_id, **kwargs):
        try:
            user = self._require_user()
            if not self._is_manager(user):
                return self._json_response({'ok': False, 'message': 'Only managers can reject plans'})

            plan = request.env['salesperson.visit.plan'].sudo().browse(plan_id)
            if not plan.exists():
                return self._json_response({'ok': False, 'message': 'Plan not found'})
            if plan.state != 'submitted':
                return self._json_response({'ok': False, 'message': f'Plan is {plan.state}, not submitted'})

            body = self._json_body()
            notes = body.get('manager_notes')
            if notes:
                plan.manager_notes = notes
            plan.action_reject()

            return self._json_response({'ok': True, 'state': plan.state})
        except Exception as e:
            _logger.error('reject_plan error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})

    # ── Push Token (cross-device Start/Stop trigger) ────────────────────────

    @http.route('/mobile/api/register_push_token', type='http', auth='user', csrf=False, methods=['POST'])
    def register_push_token(self, **kwargs):
        """Called once by the app after login (and whenever Expo rotates the
        token) so /live's Start/Stop buttons can wake this user's phone from
        any device, not just from the phone itself.
        """
        try:
            user = self._require_user()
            body = self._json_body()
            token = (body.get('expo_push_token') or '').strip()
            if not token:
                return self._json_response({'ok': False, 'message': 'No token provided'})

            user.sudo().write({'expo_push_token': token})
            _logger.info('register_push_token: user=%s token registered', user.name)
            return self._json_response({'ok': True})
        except Exception as e:
            _logger.error('register_push_token error: %s', e, exc_info=True)
            return self._json_response({'ok': False, 'message': str(e)})
