import base64
import json
import math
from datetime import date, datetime, timedelta
from pytz import timezone, utc

from odoo import fields, http, _
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
import logging
_logger = logging.getLogger(__name__)

def _localize_dt(dt, tz_name=None):
    """Convert naive UTC datetime → localized string for display. Fix #8."""
    if not dt:
        return ''
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return dt
    # dt is naive UTC (Odoo convention)
    dt_utc = utc.localize(dt)
    if tz_name:
        try:
            local_tz = timezone(tz_name)
            dt_local = dt_utc.astimezone(local_tz)
            return dt_local.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    return dt_utc.strftime('%Y-%m-%d %H:%M:%S')


class SalespersonTrackingController(http.Controller):

    def _check_access(self):
        user = request.env.user
        if user._is_public():
            raise AccessError(_("Please log in to access tracking."))
        if not hasattr(user, 'salesperson_role') or user.salesperson_role not in ("manager", "salesman"):
            raise AccessError(_("Only salespersons and managers can access tracking."))
        
        # Ensure the user has the tracker method
        if not hasattr(user, '_ensure_salesperson_tracker'):
            # Monkey patch if needed (better to add to res.users via inheritance)
            pass
        
        return user

    def _no_cache(self, response):
        """Force browsers/webviews to always re-fetch these pages instead of
        reusing a cached copy. Without this, a phone that visited /live or
        /moving_map earlier as one salesperson can keep showing that
        person's rendered page (name, position, everything) even after a
        completely different user logs in and clicks the same button —
        session-cookie auth was actually resolving correctly server-side
        the whole time; the browser was just never asking the server again."""
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    def _user_tz(self, user):
        """Return user's timezone name, falling back to UTC."""
        try:
            return user.tz or 'UTC'
        except Exception:
            return 'UTC'

    def _json_body(self):
        payload = request.httprequest.data or b"{}"
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def _compute_total_distance(self, logs):
        total, prev = 0.0, None
        for log in logs:
            if not (log.latitude and log.longitude):
                continue
            if prev:
                total += self._haversine_km(prev[0], prev[1], log.latitude, log.longitude)
            prev = (log.latitude, log.longitude)
        return round(total, 3)

    def _json_response(self, data):
        """Return a JSON HTTP response compatible with Odoo 19."""
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
        )

    # ── Pages ─────────────────────────────────────────────────────────────────

    @http.route("/salesperson_tracking/live", type="http", auth="user", website=False)
    def live_tracking_page(self, **kwargs):
     
        user = self._check_access()

        today = fields.Date.today()
        existing_tracker = request.env['salesperson.tracker'].sudo().search([
            ('user_id', '=', user.id), ('visit_date', '=', today),
        ], order='id desc', limit=1)

        if not existing_tracker:
            plan = request.env['salesperson.visit.plan'].sudo().search([
                ('user_id', '=', user.id), ('visit_date', '=', today), ('state', '=', 'approved'),
            ], limit=1)
            if not plan:
                _logger.info("live_tracking_page: uid=%s(%s) has no approved plan today — no tracker created", user.id, user.name)
                return self._no_cache(request.render("zencore_salesperson_tracking.no_active_plan_page", {'user': user}))

        tracker = user._ensure_salesperson_tracker()

     
        logs = request.env["salesperson.location.log"].sudo().search([
            ("tracker_id", "=", tracker.id)
        ], order="tracked_at asc")

        total_distance = self._compute_total_distance(logs)

        # Fix #8: Localize last_seen for display
        tz_name = self._user_tz(user)
        last_seen_display = _localize_dt(tracker.last_seen, tz_name) if tracker.last_seen else 'Not tracked'

        # Build customer pins for the live-tracking mini-map (same logic as moving_map)
        live_customers = []
        live_seen_ids = set()
        live_visited_ids = {v.partner_id.id for v in tracker.visited_line_ids}
        # Also mark currently active check-in as visited (salesperson inside geofence now)
        if tracker.current_checkin_id and tracker.current_checkin_id.partner_id:
            live_visited_ids.add(tracker.current_checkin_id.partner_id.id)

        def _add_live_partner(partner, override_visited=None):
            if not partner or partner.id in live_seen_ids:
                return
            lat = partner.partner_latitude
            lng = partner.partner_longitude
            if not lat or not lng:
                return
            visited = override_visited if override_visited is not None else (partner.id in live_visited_ids)
            live_customers.append({
                "id": partner.id,
                "name": partner.name,
                "lat": lat,
                "lng": lng,
                "visited": visited,
            })
            live_seen_ids.add(partner.id)

        for tline in tracker.target_line_ids:
            for partner in tline.customer_ids:
                _add_live_partner(partner)

        if not live_seen_ids and tracker.plan_id:
            for pline in tracker.plan_id.target_line_ids:
                for partner in pline.customer_ids:
                    _add_live_partner(partner)

        for vline in tracker.visited_line_ids:
            _add_live_partner(vline.partner_id, override_visited=True)

        live_customers_b64 = base64.b64encode(json.dumps(live_customers).encode()).decode()

        values = {
            "tracker": tracker,
            "user": user,
            "total_distance_km": total_distance,
            "today_plan_count": tracker.total_visits,
            "today_visited_count": tracker.total_visited,
            "today_rate": int(tracker.total_visited * 100 / tracker.total_visits) if tracker.total_visits else 0,
            "last_seen_display": last_seen_display,
            # /live is always the current user's own page → is_owner always True
            "is_owner": True,
            "live_customers_b64": live_customers_b64,
            # Drives whether this tab runs its own browser GPS loop, or trusts
            # the phone app's silent push-triggered background service instead
            # (see action_start_tracking/action_stop_tracking).
            "has_push_token": bool(user.expo_push_token),
        }
        _logger.info(
            "live_tracking_page: uid=%s(%s) tracker=%s is_owner=True",
            user.id, user.name, tracker.id,
        )
        return self._no_cache(request.render("zencore_salesperson_tracking.live_tracking_page", values))

    @http.route("/salesperson_tracking/moving_map/<int:tracker_id>", type="http", auth="user", website=False)
    def moving_map(self, tracker_id, **kwargs):
        user = self._check_access()
        _logger.info("moving_map: request tracker_id=%s by user=%s (id=%s)", tracker_id, user.name, user.id)

        tracker = request.env["salesperson.tracker"].sudo().browse(tracker_id)
        if not tracker.exists():
            _logger.warning("moving_map: tracker_id=%s does not exist", tracker_id)
            return request.not_found()

        _logger.info(
            "moving_map: tracker found — user=%s is_tracking=%s last_seen=%s last_lat=%s last_lng=%s",
            tracker.user_id.name, tracker.is_tracking, tracker.last_seen,
            tracker.last_latitude, tracker.last_longitude,
        )

        tracking_status = tracker.tracking_status or 'offline'
        tz_name = self._user_tz(user)

        # Show every available GPS point for this exact tracker.
        # Previously this route filtered by today's date, which meant older
        # tracking rows could exist in the database but were missing from the map.
        logs = request.env["salesperson.location.log"].sudo().search([
            ("tracker_id", "=", tracker_id),
        ], order="tracked_at asc")

        _logger.info(
            "moving_map: found %d location logs for tracker_id=%s",
            len(logs), tracker_id,
        )

        points = []
        skipped = 0
        for log in logs:
            if log.latitude and log.longitude:
                points.append({
                    "lat": log.latitude,
                    "lng": log.longitude,
                    "accuracy": log.accuracy,
                    "time": _localize_dt(log.tracked_at, tz_name),
                    "location_name": log.location_name or "",
                })
            else:
                skipped += 1

        if skipped:
            _logger.warning(
                "moving_map: skipped %d logs with missing coordinates for tracker_id=%s",
                skipped, tracker_id,
            )

        _logger.info("moving_map: %d valid GPS points for tracker_id=%s", len(points), tracker_id)

        # Fallback: if no log points exist yet, show last known position
        if not points and tracker.last_latitude and tracker.last_longitude:
            _logger.info(
                "moving_map: no log points — using last_known fallback lat=%s lng=%s",
                tracker.last_latitude, tracker.last_longitude,
            )
            points.append({
                "lat": tracker.last_latitude,
                "lng": tracker.last_longitude,
                "accuracy": tracker.last_accuracy,
                "time": _localize_dt(tracker.last_seen, tz_name),
                "location_name": tracker.location_name or "Last known position",
            })
        elif not points:
            _logger.warning(
                "moving_map: NO points available for tracker_id=%s — tracker has no last_latitude either",
                tracker_id,
            )

        points_b64 = base64.b64encode(json.dumps(points).encode()).decode()

        # ── Customer pins ──────────────────────────────────────────────────
        # Sources (in priority order):
        #   1. tracker.target_line_ids  — rows loaded by action_load_target_lines
        #   2. tracker.plan_id.target_line_ids — raw plan lines (fallback)
        #   3. tracker.visited_line_ids — visited customers not already in the plan
        # We deduplicate by partner.id to avoid double-pins.
        # Status: visited > not-yet-visited (planned) > skipped (planned but not visited and not remaining)
        customers = []
        seen_partner_ids = set()
        visited_ids   = {v.partner_id.id for v in tracker.visited_line_ids}
        # Also treat currently active check-in as visited (salesperson inside geofence right now)
        if tracker.current_checkin_id and tracker.current_checkin_id.partner_id:
            visited_ids.add(tracker.current_checkin_id.partner_id.id)
        _logger.info(
            "moving_map: building customer pins tracker=%s plan_id=%s visited_ids=%s",
            tracker_id, tracker.plan_id.id if tracker.plan_id else None, visited_ids,
        )

        def _add_partner(partner, override_visited=None):
            if not partner or partner.id in seen_partner_ids:
                return
            lat = partner.partner_latitude
            lng = partner.partner_longitude
            if not lat or not lng:
                _logger.debug(
                    "moving_map: partner %r (id=%s) has no coordinates — skipped",
                    partner.name, partner.id,
                )
                return
            visited = override_visited if override_visited is not None else (partner.id in visited_ids)
            customers.append({
                "id":      partner.id,
                "name":    partner.name,
                "lat":     lat,
                "lng":     lng,
                "visited": visited,
            })
            seen_partner_ids.add(partner.id)
            _logger.debug(
                "moving_map: customer pin added — name=%r id=%s lat=%.6f lng=%.6f visited=%s",
                partner.name, partner.id, lat, lng, visited,
            )

        # Source 1: tracker.target_line_ids (most reliable — loaded for this tracker)
        for tline in tracker.target_line_ids:
            for partner in tline.customer_ids:
                _add_partner(partner)

        # Source 2: fallback to plan lines if target_line_ids is empty
        if not seen_partner_ids and tracker.plan_id:
            _logger.info(
                "moving_map: no target_line_ids on tracker — falling back to plan_id=%s lines",
                tracker.plan_id.id,
            )
            for pline in tracker.plan_id.target_line_ids:
                for partner in pline.customer_ids:
                    _add_partner(partner)

        # Source 3: visited customers not already captured
        for vline in tracker.visited_line_ids:
            _add_partner(vline.partner_id, override_visited=True)

        _logger.info(
            "moving_map: %d customer pins for tracker_id=%s (visited=%d, pending=%d)",
            len(customers), tracker_id,
            sum(1 for c in customers if c["visited"]),
            sum(1 for c in customers if not c["visited"]),
        )

        customers_b64 = base64.b64encode(json.dumps(customers).encode()).decode()
        last_seen_display_map = _localize_dt(tracker.last_seen, tz_name) if tracker.last_seen else '—'

        values = {
            "tracker": tracker,
            "points_b64": points_b64,
            "customers_b64": customers_b64,
            "total_logs": len(points),
            "tracking_status": tracking_status,
            "tracker_id": tracker_id,
            "last_seen_display": last_seen_display_map,
            "last_known_lat": tracker.last_latitude or 0,
            "last_known_lng": tracker.last_longitude or 0,
        }
        return self._no_cache(request.render("zencore_salesperson_tracking.moving_map_page", values))

    # ── Dashboard ─────────────────────────────────────────────────────────────

    @http.route("/salesperson/dashboard", type="http", auth="user", website=False)
    def salesperson_dashboard(self, **kwargs):
        """Manager dashboard — Today (live map) / Weekly / Monthly / custom date range (reports only unless the range is exactly today)."""
        user = self._check_access()
        tz_name = self._user_tz(user)
        is_manager = getattr(user, 'salesperson_role', '') == 'manager'

        period = kwargs.get('period') if kwargs.get('period') in ('today', 'weekly', 'monthly') else 'today'
        salesman_id = int(kwargs['salesman_id']) if kwargs.get('salesman_id') else None

        today = fields.Date.today()
        Tracker = request.env["salesperson.tracker"].sudo()

        # Salesman filter dropdown — every user who has at least one tracker
        # (i.e. has actually been tracked at some point), not every res.users.
        all_trackers_ever = Tracker.search([])
        salesmen = sorted(
            {(t.user_id.id, t.user_id.name) for t in all_trackers_ever if t.user_id},
            key=lambda p: p[1] or '',
        )

        # Custom date range (date_from/date_to) takes priority over the
        # Today/Weekly/Monthly quick tabs when both are supplied — this is
        # what the date-range picker in the header submits. It falls back
        # to the period tabs' own computed range when absent, so the picker
        # always shows a sensible pre-filled range matching whichever tab
        # is currently active.
        custom_range = bool(kwargs.get('date_from') and kwargs.get('date_to'))
        if custom_range:
            try:
                date_from = fields.Date.from_string(kwargs['date_from'])
                date_to = fields.Date.from_string(kwargs['date_to'])
            except Exception:
                custom_range = False
        if custom_range:
            if date_from > date_to:
                date_from, date_to = date_to, date_from
            date_domain = [("visit_date", ">=", date_from), ("visit_date", "<=", date_to)]
            if date_from == date_to:
                period_label = date_from.strftime('%d %B %Y')
            else:
                period_label = f"{date_from.strftime('%d %b')} – {date_to.strftime('%d %b %Y')}"
            # A custom single-day range that happens to be today behaves
            # exactly like the "Today" tab (live map); anything else — a
            # past day, or any multi-day span — is report-only, same as
            # Weekly/Monthly.
            is_live = (date_from == date_to == today)
        else:
            date_domain, period_label = self._dashboard_period_domain(period, today)
            date_from, date_to = self._dashboard_period_range(period, today)
            is_live = (period == 'today')

        domain = date_domain
        if salesman_id:
            domain = domain + [("user_id", "=", salesman_id)]
        trackers = Tracker.search(domain)

        if is_live:
            rows, map_salesmen, map_customers = self._dashboard_today_rows(trackers)
        else:
            rows = self._dashboard_period_rows(trackers)
            map_salesmen, map_customers = [], []

        total_planned = sum(r['total'] for r in rows)
        total_covered = sum(r['covered'] for r in rows)
        kpi_pct = int(total_covered * 100 / total_planned) if total_planned else 0
        missed_count = sum(r['missed'] for r in rows)

        live_count = sum(1 for r in rows if r.get('status') in ('moving', 'at_customer'))
        idle_count = sum(1 for r in rows if r.get('status') == 'idle')
        offline_count = sum(1 for r in rows if r.get('status') == 'offline')

        # Activity feed only makes sense for the live view (recent GPS pings)
        activity_feed = []
        if is_live:
            log_domain = [("tracked_at", ">=", fields.Datetime.to_datetime(today))]
            if salesman_id:
                log_domain.append(("tracker_id.user_id", "=", salesman_id))
            logs = request.env["salesperson.location.log"].sudo().search(
                log_domain, order="tracked_at desc", limit=20
            )
            for log in logs:
                status = log.tracker_id._compute_dashboard_status()[0] if log.tracker_id else 'offline'
                activity_feed.append({
                    'name': log.tracker_id.user_id.name if log.tracker_id and log.tracker_id.user_id else '—',
                    'desc': log.location_name or f"{log.latitude:.4f}, {log.longitude:.4f}",
                    'time': _localize_dt(log.tracked_at, tz_name)[11:16] if log.tracked_at else '—',
                    'dot_color': Tracker.DASHBOARD_STATUS_COLORS.get(status, '#DC2626'),
                })

        my_tracker = None
        my_status = 'offline'
        my_dist = '0.0'
        my_covered = 0
        my_total = 0
        my_location = '—'
        my_checkins_today = 0
        if not is_manager:
            my_tracker = Tracker.search([('user_id', '=', user.id), ('visit_date', '=', today)], limit=1)
            if my_tracker:
                my_status = my_tracker._compute_dashboard_status()[0]
                my_dist = f"{my_tracker.total_distance_km:.1f}"
                my_covered = my_tracker.total_visited
                my_total = my_tracker.total_visits
                my_location = my_tracker.location_name or '—'
                my_checkins_today = len(my_tracker.visited_line_ids)

        values = {
            "user": user,
            "is_manager": is_manager,
            "today": today.strftime('%A, %d %B %Y'),
            "period": period if not custom_range else 'custom',
            "period_label": period_label,
            "is_live": is_live,
            "date_from_str": date_from.strftime('%Y-%m-%d'),
            "date_to_str": date_to.strftime('%Y-%m-%d'),
            "salesmen": [{"id": s[0], "name": s[1]} for s in salesmen],
            "selected_salesman_id": salesman_id,
            "rows": rows,
            "map_salesmen": map_salesmen,
            "map_customers": map_customers,
            "live_count": live_count,
            "idle_count": idle_count,
            "offline_count": offline_count,
            "total_reps": len(rows),
            "total_planned": total_planned,
            "total_covered": total_covered,
            "activity_feed": activity_feed,
            "kpi_pct": kpi_pct,
            "kpi_covered": total_covered,
            "kpi_in_progress": live_count + idle_count,
            "kpi_missed": missed_count,
            "my_tracker": my_tracker,
            "my_status": my_status,
            "my_dist": my_dist,
            "my_covered": my_covered,
            "my_total": my_total,
            "my_location": my_location,
            "my_checkins_today": my_checkins_today,
        }
        return self._no_cache(request.render("zencore_salesperson_tracking.salesperson_dashboard", values))

    def _dashboard_period_range(self, period, today):
        """(date_from, date_to) for a quick-tab period — used to pre-fill the date-range picker."""
        if period == 'weekly':
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        if period == 'monthly':
            start = today.replace(day=1)
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            return start, next_month - timedelta(days=1)
        return today, today

    def _dashboard_period_domain(self, period, today):
        """Date domain + human label for the 3 dashboard tabs."""
        if period == 'weekly':
            start = today - timedelta(days=today.weekday())  # Monday
            end = start + timedelta(days=6)
            label = f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}"
            return [("visit_date", ">=", start), ("visit_date", "<=", end)], label
        if period == 'monthly':
            start = today.replace(day=1)
            next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = next_month - timedelta(days=1)
            label = today.strftime('%B %Y')
            return [("visit_date", ">=", start), ("visit_date", "<=", end)], label
        # today
        return [("visit_date", "=", today)], today.strftime('%A, %d %B %Y')

    def _dashboard_today_rows(self, trackers):
        """Per-salesman live row + live map marker lists (Today tab only)."""
        COLORS = [
            'linear-gradient(135deg,#2563EB,#4F46E5)',
            'linear-gradient(135deg,#059669,#10B981)',
            'linear-gradient(135deg,#D97706,#F59E0B)',
            'linear-gradient(135deg,#DC2626,#E11D48)',
            'linear-gradient(135deg,#7C3AED,#A78BFA)',
        ]
        rows, map_salesmen, map_customers = [], [], []
        seen_customer_ids = set()
        for i, t in enumerate(trackers):
            status, color, label = t._compute_dashboard_status()
            name = t.user_id.name or 'Unknown'
            initials = ''.join(p[0].upper() for p in name.split()[:2])
            rows.append({
                'id': t.id, 'name': name, 'initials': initials,
                'status': status, 'status_label': label, 'status_color': color,
                'covered': t.total_visited, 'total': t.total_visits,
                'missed': max(t.total_visits - t.total_visited, 0),
                'pct': int(t.total_visited * 100 / t.total_visits) if t.total_visits else 0,
                'distance': f"{t.total_distance_km:.1f} km",
                'gradient': COLORS[i % len(COLORS)],
            })
            if t.last_latitude and t.last_longitude:
                map_salesmen.append({
                    'id': t.id, 'name': name, 'initials': initials,
                    'lat': t.last_latitude, 'lng': t.last_longitude,
                    'status': status, 'status_label': label, 'status_color': color,
                })
            for customer in t.target_line_ids.mapped('customer_ids'):
                if customer.id in seen_customer_ids:
                    continue
                if customer.partner_latitude and customer.partner_longitude:
                    seen_customer_ids.add(customer.id)
                    map_customers.append({
                        'id': customer.id, 'name': customer.name,
                        'lat': customer.partner_latitude, 'lng': customer.partner_longitude,
                    })
        return rows, map_salesmen, map_customers

    def _dashboard_period_rows(self, trackers):
        """Aggregated per-salesman totals across a date range (Weekly/Monthly — no live status)."""
        COLORS = [
            'linear-gradient(135deg,#2563EB,#4F46E5)',
            'linear-gradient(135deg,#059669,#10B981)',
            'linear-gradient(135deg,#D97706,#F59E0B)',
            'linear-gradient(135deg,#DC2626,#E11D48)',
            'linear-gradient(135deg,#7C3AED,#A78BFA)',
        ]
        by_user = {}
        for t in trackers:
            if not t.user_id:
                continue
            agg = by_user.setdefault(t.user_id.id, {
                'id': t.user_id.id, 'name': t.user_id.name, 'covered': 0, 'total': 0, 'distance_km': 0.0,
            })
            agg['covered'] += t.total_visited
            agg['total'] += t.total_visits
            agg['distance_km'] += t.total_distance_km
        rows = []
        for i, agg in enumerate(by_user.values()):
            initials = ''.join(p[0].upper() for p in agg['name'].split()[:2]) if agg['name'] else '?'
            rows.append({
                'id': agg['id'], 'name': agg['name'], 'initials': initials,
                'status': None, 'status_label': '—', 'status_color': '#94A3B8',
                'covered': agg['covered'], 'total': agg['total'],
                'missed': max(agg['total'] - agg['covered'], 0),
                'pct': int(agg['covered'] * 100 / agg['total']) if agg['total'] else 0,
                'distance': f"{agg['distance_km']:.1f} km",
                'gradient': COLORS[i % len(COLORS)],
            })
        rows.sort(key=lambda r: r['name'] or '')
        return rows

    # ── Dashboard data API (for map AJAX — Today tab live polling) ─────────────

    @http.route("/salesperson/dashboard/data", type="http", auth="user", methods=["GET"], csrf=False)
    def dashboard_data(self, **kwargs):
        """JSON endpoint the Today tab polls every few seconds to move markers
        and update statuses without a full page reload."""
        self._check_access()
        today = fields.Date.today()
        Tracker = request.env["salesperson.tracker"].sudo()
        domain = [("visit_date", "=", today)]
        salesman_id = int(kwargs['salesman_id']) if kwargs.get('salesman_id') else None
        if salesman_id:
            domain.append(("user_id", "=", salesman_id))
        trackers = Tracker.search(domain)

        salesmen_out, customers_out = [], []
        seen_customer_ids = set()
        for t in trackers:
            status, color, label = t._compute_dashboard_status()
            name = t.user_id.name or ''
            initials = ''.join(p[0].upper() for p in name.split()[:2])
            salesmen_out.append({
                "id": t.id, "name": name, "initials": initials,
                "status": status, "status_label": label, "status_color": color,
                "lat": t.last_latitude or 0, "lng": t.last_longitude or 0,
                "location": t.location_name or '',
                "covered": t.total_visited, "total": t.total_visits,
            })
            for customer in t.target_line_ids.mapped('customer_ids'):
                if customer.id in seen_customer_ids:
                    continue
                if customer.partner_latitude and customer.partner_longitude:
                    seen_customer_ids.add(customer.id)
                    customers_out.append({
                        "id": customer.id, "name": customer.name,
                        "lat": customer.partner_latitude, "lng": customer.partner_longitude,
                    })

        return self._json_response({"ok": True, "trackers": salesmen_out, "customers": customers_out})

    # ── JSON API ──────────────────────────────────────────────────────────────

    @http.route("/salesperson_tracking/geocode", type="http", auth="user", methods=["POST"], csrf=False)
    def geocode_location(self, **kwargs):
        """Reverse-geocode a lat/lng and update the tracker location_name.
        Called by the JS every ~30 s — completely separate from the 2-second
        GPS log updates so geocoding never blocks log creation.
        """
        user = self._check_access()
        payload = self._json_body()
        try:
            lat = float(payload["latitude"])
            lng = float(payload["longitude"])
        except (KeyError, ValueError):
            return self._json_response({"ok": False})

        tracker_id = payload.get("tracker_id")
        if tracker_id:
            tracker = request.env["salesperson.tracker"].sudo().browse(int(tracker_id))
        else:
            tracker = user._ensure_salesperson_tracker()

        if not tracker or not tracker.exists():
            return self._json_response({"ok": False})

        # Run the blocking Nominatim HTTP request AFTER releasing the DB cursor
        # by committing first.  This prevents the 5-second HTTP timeout from
        # holding a DB worker connection open and exhausting the pool.
        request.env.cr.commit()
        name = tracker._reverse_geocode(lat, lng)
        if name:
            # Re-open a short transaction just for the write
            request.env["salesperson.tracker"].sudo().browse(tracker.id).write(
                {"location_name": name}
            )
            _logger.debug("geocode_location: tracker=%s → %r", tracker.id, name)

        return self._json_response({"ok": True, "location_name": name or tracker.location_name or ""})

    @http.route("/salesperson_tracking/update", type="http", auth="user", methods=["POST"], csrf=False)
    def update_location(self, **kwargs):
        user = self._check_access()
        payload = self._json_body()

        try:
            latitude  = float(payload["latitude"])
            longitude = float(payload["longitude"])
        except (KeyError, ValueError) as e:
            _logger.warning("update_location: invalid payload from user=%s: %s | payload=%s", user.name, e, payload)
            return self._json_response({"ok": False, "error": "Latitude and longitude required."})

        tracker_id = payload.get("tracker_id")
        if tracker_id:
            tracker = request.env["salesperson.tracker"].sudo().browse(int(tracker_id))
            _logger.debug("update_location: using supplied tracker_id=%s for user=%s", tracker_id, user.name)
        else:
            tracker = user._ensure_salesperson_tracker()
            _logger.debug("update_location: auto-resolved tracker_id=%s for user=%s", tracker.id, user.name)

        if not tracker or not tracker.exists():
            _logger.error("update_location: no tracker found for user=%s tracker_id=%s", user.name, tracker_id)
            return self._json_response({"ok": False, "error": "No tracker found."})

        _logger.info(
            "update_location: user=%s tracker=%s lat=%.6f lng=%.6f accuracy=%s distance=%s",
            user.name, tracker.id, latitude, longitude,
            payload.get("accuracy"), payload.get("distance"),
        )

        try:
            tracker.update_live_location(
                latitude=latitude,
                longitude=longitude,
                accuracy=payload.get("accuracy"),
                source="browser",
                distance=float(payload.get("distance") or 0.0),
            )
        except Exception as e:
            _logger.error(
                "update_location: update_live_location failed for tracker=%s user=%s: %s",
                tracker.id, user.name, e, exc_info=True,
            )
            return self._json_response({
                "ok": False,
                "error": str(e),
                "tracker_id": tracker.id,
            })

        # Read back the fields we need directly from SQL — the previous
        # update_live_location() call used raw SQL so the ORM cache may be
        # stale.  A direct SQL SELECT guarantees we see the committed values
        # without triggering any ORM recomputes or field dependencies.
        request.env.cr.execute(
            """
            SELECT is_tracking, last_seen, last_latitude, last_longitude,
                   total_distance_km, location_name
              FROM salesperson_tracker
             WHERE id = %s
            """,
            (tracker.id,),
        )
        row = request.env.cr.fetchone()
        if not row:
            return self._json_response({"ok": False, "error": "Tracker not found."})

        is_tracking_db, last_seen_db, lat_db, lng_db, dist_db, loc_db = row
        total_distance = round(dist_db or 0.0, 3)

        tz_name = self._user_tz(user)
        last_seen_local = _localize_dt(last_seen_db, tz_name) if last_seen_db else ""

        map_url = (
            f"https://www.openstreetmap.org/?mlat={lat_db}&mlon={lng_db}"
            f"#map=16/{lat_db}/{lng_db}"
            if lat_db and lng_db else ""
        )

        # Fast log count for the live "Logs: N" counter in the UI
        request.env.cr.execute(
            "SELECT COUNT(*) FROM salesperson_location_log WHERE tracker_id = %s",
            (tracker.id,),
        )
        total_logs = request.env.cr.fetchone()[0]

        _logger.debug(
            "update_location: returning ok=True tracker=%s is_tracking=%s distance=%.3f logs=%d",
            tracker.id, is_tracking_db, total_distance, total_logs,
        )

        # ── Near-customer proximity check ────────────────────────────────────
        # Returns the nearest customer within geofence radius so the live map
        # can turn the position marker green when the salesperson is nearby.
        near_customer = None
        try:
            geofence_radius = float(request.env["ir.config_parameter"].sudo().get_param(
                "zencore_salesperson_tracking.geofence_radius", "100"
            ))
            tracker_obj = request.env["salesperson.tracker"].sudo().browse(tracker.id)
            if tracker_obj.plan_id:
                lines = request.env["salesperson.visit.plan.line"].sudo().search([
                    ("plan_id", "=", tracker_obj.plan_id.id),
                ])
                partner_ids = lines.mapped("customer_ids").filtered(
                    lambda p: p.partner_latitude and p.partner_longitude
                ).ids
                if partner_ids:
                    nearest_dist = float("inf")
                    nearest_name = None
                    visited_ids = {v.partner_id.id for v in tracker_obj.visited_line_ids}
                    for p in request.env["res.partner"].sudo().browse(partner_ids):
                        if not (p.partner_latitude and p.partner_longitude):
                            continue
                        d = self._haversine_km(lat_db, lng_db, p.partner_latitude, p.partner_longitude) * 1000
                        if d < nearest_dist:
                            nearest_dist = d
                            nearest_name = p.display_name
                            nearest_visited = p.id in visited_ids
                    if nearest_dist <= geofence_radius:
                        near_customer = {"name": nearest_name, "distance_m": round(nearest_dist, 1), "visited": nearest_visited}
        except Exception as _e:
            _logger.debug("near_customer check failed: %s", _e)

        return self._json_response({
            "ok": True,
            "tracker_id": tracker.id,
            "status": "live" if is_tracking_db else "offline",
            "status_label": "Live" if is_tracking_db else "Offline",
            "is_tracking": is_tracking_db,
            "last_seen": last_seen_local,
            "latitude": lat_db,
            "longitude": lng_db,
            "location_name": loc_db or "",
            "map_url": map_url,
            "total_distance_km": total_distance,
            "total_logs": total_logs,
            "near_customer": near_customer,
            "visited_count": tracker.total_visited,
            "visited_rate": int(tracker.total_visited * 100 / tracker.total_visits) if tracker.total_visits else 0,
            "planned_count": tracker.total_visits,
        })

    @http.route("/salesperson_tracking/debug/<int:tracker_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def debug_tracker(self, tracker_id, **kw):
        """Raw diagnostic endpoint — reads directly from SQL, no ORM cache.
        Access: /salesperson_tracking/debug/<tracker_id>
        Returns JSON with full tracker + recent log stats for debugging."""
        user = request.env.user
        request.env.cr.execute(
            """
            SELECT
                t.id, t.is_tracking, t.last_seen, t.last_latitude, t.last_longitude,
                t.last_accuracy, t.total_distance_km, t.location_name,
                t.create_date,
                (SELECT COUNT(*) FROM salesperson_location_log l WHERE l.tracker_id = t.id) AS total_logs,
                (SELECT COUNT(*) FROM salesperson_location_log l
                    WHERE l.tracker_id = t.id
                    AND l.tracked_at >= NOW() - INTERVAL '2 minutes') AS logs_last_2min,
                (SELECT COUNT(*) FROM salesperson_location_log l
                    WHERE l.tracker_id = t.id
                    AND l.tracked_at >= NOW() - INTERVAL '10 minutes') AS logs_last_10min,
                (SELECT MAX(l.tracked_at) FROM salesperson_location_log l WHERE l.tracker_id = t.id) AS last_log_at,
                (SELECT MIN(l.tracked_at) FROM salesperson_location_log l
                    WHERE l.tracker_id = t.id
                    AND l.tracked_at >= NOW() - INTERVAL '10 minutes') AS first_recent_log_at
            FROM salesperson_tracker t
            WHERE t.id = %s
            """,
            (tracker_id,),
        )
        row = request.env.cr.fetchone()
        if not row:
            return self._json_response({"ok": False, "error": "Tracker not found"})

        cols = ["id","is_tracking","last_seen","last_latitude","last_longitude",
                "last_accuracy","total_distance_km","location_name","create_date",
                "total_logs","logs_last_2min","logs_last_10min","last_log_at","first_recent_log_at"]
        data = dict(zip(cols, row))

        # Convert datetimes to strings
        for k in ("last_seen","create_date","last_log_at","first_recent_log_at"):
            if data[k]:
                data[k] = str(data[k])

        data["ok"] = True
        data["server_now"] = str(request.env.cr.execute("SELECT NOW()") or "") 
        request.env.cr.execute("SELECT NOW()")
        data["server_now"] = str(request.env.cr.fetchone()[0])
        data["requesting_user"] = user.login

        _logger.info("debug_tracker: tracker=%s data=%s", tracker_id, data)
        return self._json_response(data)

    @http.route("/salesperson_tracking/moving_map_data/<int:tracker_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def moving_map_data(self, tracker_id, **kwargs):
        """JSON endpoint: returns all available location points + current tracking status for live map polling."""
        user = self._check_access()
        tracker = request.env["salesperson.tracker"].sudo().browse(tracker_id)
        if not tracker.exists():
            _logger.warning("moving_map_data: tracker_id=%s not found", tracker_id)
            return self._json_response({"ok": False, "error": "Tracker not found"})
        
        logs = request.env["salesperson.location.log"].sudo().search([
            ("tracker_id", "=", tracker_id),
        ], order="tracked_at asc")
        
        tz_name = self._user_tz(user)
        points = []
        skipped = 0
        for log in logs:
            if log.latitude and log.longitude:
                points.append({
                    "lat": log.latitude,
                    "lng": log.longitude,
                    "time": _localize_dt(log.tracked_at, tz_name),
                    "accuracy": log.accuracy,
                    "location_name": log.location_name or "",
                })
            else:
                skipped += 1

        if skipped:
            _logger.debug(
                "moving_map_data: tracker_id=%s skipped %d logs with missing coords",
                tracker_id, skipped,
            )

        # Fallback: use last known position when no log points yet
        if not points and tracker.last_latitude and tracker.last_longitude:
            _logger.info(
                "moving_map_data: tracker_id=%s has no log points — using last_known fallback lat=%s lng=%s",
                tracker_id, tracker.last_latitude, tracker.last_longitude,
            )
            points.append({
                "lat": tracker.last_latitude,
                "lng": tracker.last_longitude,
                "time": _localize_dt(tracker.last_seen, tz_name) if tracker.last_seen else "",
                "accuracy": tracker.last_accuracy,
                "location_name": tracker.location_name or "",
            })

        total_dist = self._compute_total_distance(logs)

        _logger.debug(
            "moving_map_data: tracker_id=%s status=%s points=%d total_dist=%.3f",
            tracker_id, tracker.tracking_status, len(points), total_dist,
        )

        # status = "live" when is_tracking=True, "offline" otherwise (idle removed)
        status = "live" if tracker.is_tracking else "offline"

        # Build visited_ids set for customer pin coloring on moving map
        # Include both completed visits (visited_line_ids) and currently active check-in
        visited_ids_set = {v.partner_id.id for v in tracker.visited_line_ids}
        if tracker.current_checkin_id and tracker.current_checkin_id.partner_id:
            visited_ids_set.add(tracker.current_checkin_id.partner_id.id)

        # Build customers list (for moving map to update pins without page reload)
        customers_live = []
        seen_ids = set()
        if tracker.plan_id:
            for line in tracker.plan_id.target_line_ids:
                for p in line.customer_ids:
                    if p.id in seen_ids:
                        continue
                    seen_ids.add(p.id)
                    if p.partner_latitude and p.partner_longitude:
                        customers_live.append({
                            "id": p.id,
                            "name": p.display_name,
                            "lat": p.partner_latitude,
                            "lng": p.partner_longitude,
                            "visited": p.id in visited_ids_set,
                        })

        return self._json_response({
            "ok": True,
            "status": status,
            "status_label": "Live" if tracker.is_tracking else "Offline",
            "is_tracking": tracker.is_tracking,
            "points": points,
            "last_lat": tracker.last_latitude or 0,
            "last_lng": tracker.last_longitude or 0,
            "last_seen": _localize_dt(tracker.last_seen, tz_name) if tracker.last_seen else "",
            "total_distance_km": total_dist,
            "customers": customers_live,
        })

    @http.route("/salesperson_tracking/start", type="http", auth="user", methods=["POST"], csrf=False)
    def start_tracking(self, **kwargs):
        """Start tracking — idempotent. Multiple tabs calling this won't create duplicate sessions."""
        try:
            user = self._check_access()
            payload = self._json_body()
            tracker_id = payload.get("tracker_id")

            if tracker_id:
                tracker = request.env["salesperson.tracker"].sudo().browse(int(tracker_id))
            else:
                tracker = user._ensure_salesperson_tracker()

            if not tracker or not tracker.exists():
                _logger.error("start_tracking: no tracker for user=%s", user.name)
                return self._json_response({"ok": False, "error": "No tracker found"})

            # Stop any OTHER active trackers for this user (same day, different tracker)
            other_active = request.env["salesperson.tracker"].sudo().search([
                ("user_id", "=", user.id),
                ("is_tracking", "=", True),
                ("id", "!=", tracker.id),
            ])
            for other in other_active:
                _logger.info(
                    "start_tracking: auto-stopping stale tracker=%s for user=%s",
                    other.id, user.name,
                )
                other.action_stop_tracking()

            was_tracking = tracker.is_tracking
            
            # Call action_start_tracking and catch any errors
            try:
                tracker.action_start_tracking()
            except Exception as e:
                _logger.error("start_tracking: action_start_tracking failed: %s", e, exc_info=True)
                return self._json_response({"ok": False, "error": str(e)})

            _logger.info(
                "start_tracking: user=%s tracker=%s was_tracking=%s → is_tracking=%s session=%s",
                user.name, tracker.id, was_tracking, tracker.is_tracking,
                tracker.current_session_id.id if tracker.current_session_id else None,
            )
            
            # tracker.refresh()
            # Invalidate cache instead of refresh (refresh doesn't exist in Odoo)
            tracker.invalidate_recordset()
            
            # Re-fetch tracker data to ensure we have latest values
            tracker = request.env["salesperson.tracker"].sudo().browse(tracker.id)
            
            return self._json_response({
                "ok": True,
                "tracker_id": tracker.id,
                "already_active": was_tracking,
                "session_id": tracker.current_session_id.id if tracker.current_session_id else None,
                "checkin_time": str(tracker.checkin_time) if tracker.checkin_time else None,
            })
        except Exception as e:
            _logger.error("start_tracking: unexpected error: %s", e, exc_info=True)
            return self._json_response({"ok": False, "error": str(e)})

    @http.route("/salesperson_tracking/stop", type="http", auth="user", methods=["POST"], csrf=False)
    def stop_tracking(self, **kwargs):
        """Stop tracking — broadcasts stop to all open tabs via the status endpoint."""
        user = self._check_access()
        payload = self._json_body()
        tracker_id = payload.get("tracker_id")

        if tracker_id:
            tracker = request.env["salesperson.tracker"].sudo().browse(int(tracker_id))
        else:
            tracker = user._ensure_salesperson_tracker()

        if not tracker or not tracker.exists():
            _logger.error("stop_tracking: no tracker for user=%s", user.name)
            return self._json_response({"ok": False, "error": "No tracker found"})

        tracker.action_stop_tracking()
        _logger.info(
            "stop_tracking: user=%s tracker=%s stopped → checkout_time=%s",
            user.name, tracker.id, tracker.checkout_time,
        )
        return self._json_response({
            "ok": True,
            "checkout_time": str(tracker.checkout_time) if tracker.checkout_time else None,
        })

    @http.route("/salesperson_tracking/status/<int:tracker_id>", type="http", auth="user", methods=["GET"], csrf=False)
    def tracking_status(self, tracker_id, **kwargs):
        """Lightweight polling endpoint. All open tabs use this to stay in sync.
        Returns is_tracking + checkin/checkout so every tab reflects the real DB state
        regardless of which tab started or stopped tracking."""
        user = self._check_access()
        tracker = request.env["salesperson.tracker"].sudo().browse(tracker_id)
        if not tracker.exists():
            return self._json_response({"ok": False, "error": "Tracker not found"})

        # Read directly from SQL — same worker that handled /update may have
        # a stale ORM cache for is_tracking after our raw SQL writes.
        request.env.cr.execute(
            """
            SELECT is_tracking, last_latitude, last_longitude, last_seen,
                   checkin_time, checkout_time, location_name
              FROM salesperson_tracker WHERE id = %s
            """,
            (tracker_id,),
        )
        row = request.env.cr.fetchone()
        if not row:
            return self._json_response({"ok": False, "error": "Tracker not found"})
        is_tracking_db, lat, lng, last_seen, checkin, checkout, loc = row

        tz_name = self._user_tz(user)
        _logger.debug(
            "tracking_status: tracker=%s is_tracking=%s (SQL)",
            tracker_id, is_tracking_db,
        )

        # Build customers for live-map pin sync
        tracker_obj = request.env["salesperson.tracker"].sudo().browse(tracker_id)
        visited_ids_set = {v.partner_id.id for v in tracker_obj.visited_line_ids}
        # Also mark currently active check-in customer as visited (inside geofence now)
        if tracker_obj.current_checkin_id and tracker_obj.current_checkin_id.partner_id:
            visited_ids_set.add(tracker_obj.current_checkin_id.partner_id.id)
        status_customers = []
        seen = set()
        for source in [tracker_obj.target_line_ids, tracker_obj.plan_id.target_line_ids if tracker_obj.plan_id else []]:
            for line in source:
                for p in line.customer_ids:
                    if p.id in seen or not (p.partner_latitude and p.partner_longitude):
                        continue
                    seen.add(p.id)
                    status_customers.append({
                        "id": p.id, "name": p.name,
                        "lat": p.partner_latitude, "lng": p.partner_longitude,
                        "visited": p.id in visited_ids_set,
                    })
            if seen:
                break

        return self._json_response({
            "ok": True,
            "is_tracking": is_tracking_db,
            "status": "live" if is_tracking_db else "offline",
            "status_label": "Live" if is_tracking_db else "Offline",
            "last_lat": lat or 0,
            "last_lng": lng or 0,
            "last_seen": _localize_dt(last_seen, tz_name) if last_seen else "",
            "checkin_time": _localize_dt(checkin, tz_name) if checkin else "",
            "checkout_time": _localize_dt(checkout, tz_name) if checkout else "",
            "location_name": loc or "",
            "customers": status_customers,
        })
    

    @http.route(
        '/salesperson_tracking/mobile/start',
        type='http', auth='user', csrf=False, methods=['POST'],
    )
    def mobile_start_tracking(self, **kwargs):
        """Mobile app check-in — requires approved plan for today."""
        try:
            user = self._check_access()

            today = fields.Date.today()
            plan = request.env['salesperson.visit.plan'].sudo().search([
                ('user_id', '=', user.id),
                ('visit_date', '=', today),
                ('state', '=', 'approved'),
            ], limit=1)

            if not plan:
                return self._json_response({
                    'status': 'no_plan',
                    'message': 'No approved visit plan for today.',
                })

            tracker = user._ensure_salesperson_tracker()
            tracker.action_start_tracking()
            return self._json_response({
                'status': 'ok',
                'tracker_id': tracker.id,
                'plan_id': plan.id,
                'plan_name': plan.name,
            })
        except Exception as e:
            _logger.error("mobile_start_tracking error: %s", e)
            return self._json_response({'status': 'error', 'message': str(e)})

    @http.route(
        '/salesperson_tracking/mobile/stop',
        type='http', auth='user', csrf=False, methods=['POST'],
    )
    def mobile_stop_tracking(self, **kwargs):
        """Mobile app check-out — stop tracker session."""
        try:
            user = self._check_access()
            tracker = user._ensure_salesperson_tracker()
            tracker.action_stop_tracking()
            return self._json_response({'status': 'ok'})
        except Exception as e:
            _logger.error("mobile_stop_tracking error: %s", e)
            return self._json_response({'status': 'error', 'message': str(e)})

    @http.route(
        '/salesperson_tracking/mobile/ping',
        type='http', auth='user', csrf=False, methods=['POST'],
    )
    def mobile_ping_location(self, **kwargs):
        """
        Background GPS push from mobile app.
        Called every 30s by Expo background task — even when app is killed.
        Body: { latitude, longitude, accuracy, distance }
        """
        try:
            body = self._json_body()
            latitude  = float(body.get('latitude', 0))
            longitude = float(body.get('longitude', 0))
            accuracy  = float(body.get('accuracy', 0))
            distance  = float(body.get('distance', 0))

            # log_time: epoch milliseconds of the TRUE on-device GPS capture
            # moment, sent by the mobile app (see locationTask.js / odooApi.js).
            # Queued-while-offline points are flushed together on reconnect,
            # so without this every queued point would get tracked_at == the
            # flush moment instead of when it was actually captured.
            log_time = None
            raw_log_time = body.get('log_time')
            if raw_log_time not in (None, '', 0):
                try:
                    log_time = datetime.utcfromtimestamp(float(raw_log_time) / 1000.0)
                except (TypeError, ValueError, OSError):
                    log_time = None

            user = request.env.user
            if user._is_public():
                return self._json_response({'status': 'unauthorized'})

            tracker = user._ensure_salesperson_tracker()

            if not tracker.is_tracking:
                # Tracker not active — silently ignore (session may have expired)
                return self._json_response({'status': 'not_tracking'})

            tracker.update_live_location(
                latitude, longitude,
                accuracy=accuracy,
                source='mobile',
                distance=distance,
                log_time=log_time,
            )

            # Reverse-geocode at most once per 30s — mirrors the browser's own
            # throttled /geocode call. Without this, trackers driven purely by
            # the mobile app's background pings never get a location_name,
            # since update_live_location deliberately skips geocoding to avoid
            # blocking the fast 2-second position writes.
            now = fields.Datetime.now()
            should_geocode = (
                not tracker.last_geocode_at
                or (now - tracker.last_geocode_at).total_seconds() > 30
            )
            if should_geocode:
                request.env.cr.commit()
                name = tracker._reverse_geocode(latitude, longitude)
                if name:
                    request.env['salesperson.tracker'].sudo().browse(tracker.id).write({
                        'location_name': name,
                        'last_geocode_at': now,
                    })
                else:
                    request.env['salesperson.tracker'].sudo().browse(tracker.id).write({
                        'last_geocode_at': now,
                    })

            return self._json_response({'status': 'ok'})

        except Exception as e:
            _logger.error("mobile_ping_location error: %s", e, exc_info=True)
            return self._json_response({'status': 'error', 'message': str(e)})

