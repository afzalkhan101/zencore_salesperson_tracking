from datetime import timedelta
import math
import logging
import time
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import requests
from .verified_gps import verified_distance_km

_logger = logging.getLogger(__name__)


class SalespersonTracker(models.Model):
    _name = "salesperson.tracker"
    _description = "Salesperson Tracking Report"
    _order = "id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]


    # Basic Info (from Visit Plan)
    name = fields.Char(string="Reference", compute="_compute_name", store=True)
    user_id = fields.Many2one("res.users", string="Salesman", required=True, tracking=True)
    sales_person = fields.Char(string="Sales Person")
    plan_id = fields.Many2one("salesperson.visit.plan", string="Visit Plan", ondelete="set null")
    company_id = fields.Many2one("res.company", related="user_id.company_id", store=True)
    sale_team_id = fields.Many2one("crm.team", related="user_id.sale_team_id", store=True)

    purpose = fields.Selection(related="plan_id.purpose", string="Purpose", store=True)
    visit_date = fields.Date(string="Visit Date", required=True, default=fields.Date.context_today)
    priority = fields.Selection([
        ("0", "Normal"),
        ("1", "High"),
        ("2", "Urgent"),
    ], default="0")

    # Counts
    total_visits = fields.Integer(string="Total Visits", compute="_compute_counts", store=True)
    total_visited = fields.Integer(string="Visited", compute="_compute_counts", store=True)
    skipped_visits = fields.Integer(string="Skipped Visits", compute="_compute_counts", store=True)

    # Timing
    checkin_time = fields.Datetime(string="First Check-In")
    checkout_time = fields.Datetime(string="Last Check-Out")
    duration_hours = fields.Float(string="Duration (Hours)", compute="_compute_duration", store=True)
    duration_minutes = fields.Float(string="Duration (Min)", compute="_compute_duration", store=True)

    # Expenses Claim (Left group - Planned)
    transport_cost = fields.Float(string="Transport Cost")
    food_cost = fields.Float(string="Food Cost")
    other_cost = fields.Float(string="Other Cost")
    total_cost = fields.Float(string="Total Cost", compute="_compute_costs", store=True)

    # Actual Expenses (Right group)
    actual_transport_cost = fields.Float(string="Actual Transport")
    actual_food_cost = fields.Float(string="Actual Food")
    actual_other_cost = fields.Float(string="Actual Other")
    actual_total_cost = fields.Float(string="Actual Total", compute="_compute_actual_costs", store=True)

    def _recalculate_verified_distance(self):
        """Rebuild persisted distance from recorded GPS logs (also repairs historical totals)."""
        for tracker in self:
            self.env.cr.execute("""
                SELECT latitude, longitude, accuracy, tracked_at
                  FROM salesperson_location_log
                 WHERE tracker_id = %s
                 ORDER BY tracked_at ASC, id ASC
            """, (tracker.id,))
            value = verified_distance_km(self.env.cr.fetchall())
            self.env.cr.execute(
                "UPDATE salesperson_tracker SET total_distance_km = %s WHERE id = %s",
                (value, tracker.id),
            )
            tracker.invalidate_recordset(['total_distance_km'])

    @api.model
    def cron_recalculate_verified_distances(self):
        """Optional batch repair for older GPS history; invoke in Odoo shell."""
        for batch_start in range(0, self.search_count([]), 100):
            self.search([], order='id', offset=batch_start, limit=100)._recalculate_verified_distance()

    # Tracking Stats
    total_distance_km = fields.Float(string="Total Distance Covered (KM)", default=0.0)
    total_tracking_time_seconds = fields.Integer(string="Total Tracking Time (sec)", default=0)
    total_tracking_time_minutes = fields.Float(string="Total Tracking Time (min)", compute="_compute_tracking_minutes", store=True)
    total_visit_time_minutes = fields.Float(string="Total Time Spent in Visits (min)", default=0.0)
    traveling_time_minutes = fields.Float(string="Traveling Time (min)", compute="_compute_traveling_time", store=True)

    # Live Tracking
    is_tracking = fields.Boolean(string="Tracking Active", default=False)
    last_seen = fields.Datetime(string="Last Update")
    last_latitude = fields.Float(string="Last Latitude", digits=(16, 7))
    last_longitude = fields.Float(string="Last Longitude", digits=(16, 7))
    last_accuracy = fields.Float(string="Accuracy (m)", digits=(16, 2))
    location_name = fields.Char(string="Current Location")
    last_geocode_at = fields.Datetime(string="Last Geocode At", help="Throttle marker — mobile ping path reverse-geocodes at most once per 30s, mirroring the web page's own JS timer.")
    openstreetmap_url = fields.Char(compute="_compute_map_url")

    # Tracking Status
    tracking_status = fields.Selection(
        [("live", "Live"), ("offline", "Offline")],
        compute="_compute_tracking_status",
        search="_search_tracking_status",
    )
    tracking_status_label = fields.Char(compute="_compute_tracking_status")

    is_own_tracker = fields.Boolean(
        string="Is Own Tracker", compute="_compute_is_own_tracker",
        help="True only for the salesman assigned to this record. Drives 'Live Page' "
             "button visibility — only the assigned salesman may open the interactive "
             "Start/Stop page; everyone else (including managers) gets read-only Map.",
    )

    def _compute_is_own_tracker(self):
        for tracker in self:
            tracker.is_own_tracker = tracker.user_id.id == self.env.user.id

    # Current Session
    current_session_id = fields.Many2one("salesperson.tracking.session", string="Current Session")
    current_checkin_id = fields.Many2one("salesperson.checkin", string="Current Check-In")

    state = fields.Selection([
        ("planned", "Planned"),
        ("offline", "Offline"),
        ("live", "Live"),
        ("completed", "Completed"),
    ], default="planned", tracking=True)

    # Tabs
    target_line_ids = fields.One2many("salesperson.tracker.target.line", "tracker_id", string="Target Lines")
    visited_line_ids = fields.One2many("salesperson.tracker.visited.line", "tracker_id", string="Visited Lines")
    session_ids = fields.One2many("salesperson.tracking.session", "tracker_id", string="Tracking Sessions")
    idle_line_ids = fields.One2many("salesperson.tracker.idle.line", "tracker_id", string="Idle Time")
    last_idle_compute_at = fields.Datetime(
        string="Last Idle Compute At",
        help="Throttle marker for the periodic idle-time cron — avoids rescanning the "
             "full day's location log on every single ping.",
    )
    related_notes = fields.Html(string="Related Notes")

    @api.depends("user_id", "plan_id")
    def _compute_name(self):
        for tracker in self:
            tracker.name = f"{tracker.user_id.name} - {tracker.visit_date}" if tracker.user_id else "New"

    @api.depends("plan_id.target_line_ids.customer_ids", "visited_line_ids.checkin_time")
    def _compute_counts(self):
        for tracker in self:
            # Total visits from plan
            total = 0
            for line in tracker.plan_id.target_line_ids:
                total += len(line.customer_ids) if line.customer_ids else 0
            tracker.total_visits = total
            
            # Only count visits that have checkin_time (completed visits)
            completed_visits = tracker.visited_line_ids.filtered(lambda v: v.checkin_time)
            tracker.total_visited = len(completed_visits)
            tracker.skipped_visits = tracker.total_visits - tracker.total_visited
            
            _logger.debug("_compute_counts: tracker=%s total_visits=%s total_visited=%s skipped=%s",
                        tracker.id, tracker.total_visits, tracker.total_visited, tracker.skipped_visits)

    @api.depends("transport_cost", "food_cost", "other_cost")
    def _compute_costs(self):
        for tracker in self:
            tracker.total_cost = tracker.transport_cost + tracker.food_cost + tracker.other_cost

    @api.depends("actual_transport_cost", "actual_food_cost", "actual_other_cost")
    def _compute_actual_costs(self):
        for tracker in self:
            tracker.actual_total_cost = tracker.actual_transport_cost + tracker.actual_food_cost + tracker.actual_other_cost

    @api.depends("checkin_time", "checkout_time")
    def _compute_duration(self):
        for tracker in self:
            if tracker.checkin_time and tracker.checkout_time:
                delta = tracker.checkout_time - tracker.checkin_time
                total_secs = delta.total_seconds()
                tracker.duration_hours = round(total_secs / 3600.0, 2)
                tracker.duration_minutes = round(total_secs / 60.0, 2)
            else:
                tracker.duration_hours = 0.0
                tracker.duration_minutes = 0.0

    @api.depends("total_tracking_time_seconds")
    def _compute_tracking_minutes(self):
        for tracker in self:
            tracker.total_tracking_time_minutes = round(tracker.total_tracking_time_seconds / 60.0, 2)

    @api.depends("total_tracking_time_seconds", "total_visit_time_minutes")
    def _compute_traveling_time(self):
        for tracker in self:
            tracking_minutes = tracker.total_tracking_time_seconds / 60.0
            tracker.traveling_time_minutes = tracking_minutes - tracker.total_visit_time_minutes

    @api.depends("last_latitude", "last_longitude")
    def _compute_map_url(self):
        for tracker in self:
            if tracker.last_latitude and tracker.last_longitude:
                tracker.openstreetmap_url = (
                    f"https://www.openstreetmap.org/?mlat={tracker.last_latitude}"
                    f"&mlon={tracker.last_longitude}#map=16/{tracker.last_latitude}/{tracker.last_longitude}"
                )
            else:
                tracker.openstreetmap_url = False

    @api.depends("is_tracking")
    def _compute_tracking_status(self):
        """Two states only: live (is_tracking=True) or offline (is_tracking=False).
        Idle removed — salesperson is live until they explicitly press Stop."""
        for tracker in self:
            status = "live" if tracker.is_tracking else "offline"
            tracker.tracking_status = status
            tracker.tracking_status_label = "Live" if tracker.is_tracking else "Offline"

    def _search_tracking_status(self, operator, value):
        mapping = {
            "live":    [("is_tracking", "=", True)],
            "offline": [("is_tracking", "=", False)],
        }
        if operator != "=" or value not in mapping:
            return []
        return mapping[value]

    def update_live_location(self, latitude, longitude, accuracy=None, source="browser", distance=0.0, log_time=None):
        """Record a live GPS position.

        log_time: optional datetime — the TRUE moment the GPS fix was captured
        on the device (as opposed to the moment this HTTP request reached the
        server). Mobile pings that were queued while offline and flushed later
        arrive here long after capture; using server-receive time for tracked_at
        made every queued point look like it happened "now", bunching widely
        separated points together and confusing the frontend's gap-detection
        (segments got merged into one straight line instead of a dashed
        reconnect). last_seen/last_latitude etc. still use server "now" — those
        describe live status, not history — but tracked_at (the log row used to
        draw the route) uses log_time when the caller provides one.

        IMPORTANT: We intentionally do NOT write salesperson coordinates to
        res.partner.partner_latitude / partner_longitude.  Those fields belong
        to *customer* partners and writing the salesperson's GPS position there
        corrupts the customer pins shown on the moving map.

        Every call — whether the position changed or not — creates a new log entry.
        The JS sends every 2 seconds, and each send must produce a row so the
        moving-map path and log count are always up to date.

        Transaction safety: we use raw SQL for the UPDATE and INSERT to avoid
        ORM recomputes and lock contention.  We do NOT call cr.rollback() —
        Odoo's service_model.retrying() wrapper handles that at the HTTP layer.
        The geofence check runs inside a SAVEPOINT so its failures cannot
        corrupt the cursor and roll back the position data we already wrote.
        """
        self.ensure_one()
        _logger.debug(
            "update_live_location: tracker=%s user=%s lat=%.6f lng=%.6f accuracy=%s source=%s",
            self.id, self.user_id.name, latitude, longitude, accuracy, source,
        )

        try:
            # Invalidate the ORM cache so the next field read hits the DB.
            self.invalidate_recordset()

            now = fields.Datetime.now()

            # Sanity-clamp log_time: only trust it if it's a plausible capture
            # moment (not more than 1 day in the past, not in the future beyond
            # a bit of clock skew). Anything outside that range falls back to
            # server-receive time rather than corrupting the log with garbage.
            tracked_at = now
            if log_time is not None:
                skew_ok = (now - log_time) <= timedelta(days=1) and (log_time - now) <= timedelta(minutes=5)
                if skew_ok:
                    tracked_at = log_time
                else:
                    _logger.warning(
                        "update_live_location: log_time %s out of plausible range vs now %s — using server time",
                        log_time, now,
                    )

            # ── Location name: NEVER call _reverse_geocode here ──────────────
            # Geocoding makes a blocking HTTP request (up to 5 s timeout) which
            # holds the DB transaction open and causes serialization failures that
            # silently drop every log entry. Reuse the last known name; the JS
            # calls /salesperson_tracking/geocode separately (throttled, async).
            location_name = self.location_name or ""

            # ── 1. Update tracker position using a single atomic SQL UPDATE ──
            # We use raw SQL for two reasons:
            #   a) total_distance_km += delta must be atomic (no read-modify-write
            #      race between concurrent worker requests for the same tracker).
            #   b) We do NOT write is_tracking here — it is already True (set by
            #      action_start_tracking).  Writing it on every tick triggers ORM
            #      recomputes and row-level locks that cause serialization failures.
            self.env.cr.execute(
                """
                UPDATE salesperson_tracker
                   SET last_seen          = %s,
                       last_latitude      = %s,
                       last_longitude     = %s,
                       last_accuracy      = %s,
                       total_distance_km  = total_distance_km,
                       location_name      = %s
                 WHERE id = %s
                """,
                (
                    now,
                    latitude,
                    longitude,
                    accuracy or 0.0,
                    location_name,
                    self.id,
                ),
            )
            # Invalidate ORM cache so subsequent field reads are fresh
            self.invalidate_recordset()
            _logger.debug("update_live_location: tracker updated ok (SQL)")

            # ── 2. Append location log — separate INSERT, no FK recomputes ──
            self.env.cr.execute(
                """
                INSERT INTO salesperson_location_log
                    (tracker_id, user_id, tracked_at, latitude, longitude, accuracy, source,
                     location_name, create_uid, write_uid, create_date, write_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                """,
                (
                    self.id,
                    self.user_id.id,
                    tracked_at,
                    latitude,
                    longitude,
                    accuracy or 0.0,
                    source,
                    location_name,
                    self.env.uid,
                    self.env.uid,
                ),
            )
            self._recalculate_verified_distance()
            # Retrieve the new log id for logging
            self.env.cr.execute("SELECT lastval()")
            log_id = self.env.cr.fetchone()[0]
            _logger.debug("update_live_location: log created id=%s (SQL)", log_id)

            # ── 3. Geofence check ─────────────────────────────────────────
            # Runs directly in the transaction (no SAVEPOINT).
            # The SAVEPOINT was causing silent rollbacks of check-in creation
            # because flush_all() inside it was re-raising ORM constraint errors.
            try:
                self._check_geofence(latitude, longitude)
                # Flush ORM writes (checkin create, current_checkin_id, visited_line)
                # and invalidate cache so total_visited is fresh in the response.
                self.env.flush_all()
                self.invalidate_recordset()
            except Exception as gf_err:
                _logger.warning(
                    "update_live_location: geofence check failed for tracker %s: %s",
                    self.id, gf_err, exc_info=True,
                )

            _logger.info(
                "update_live_location: SUCCESS tracker=%s user=%s lat=%.6f lng=%.6f log_id=%s",
                self.id, self.user_id.name, latitude, longitude, log_id,
            )

        except Exception as e:
            # Do NOT call cr.rollback() here — Odoo's service_model.retrying()
            # wrapper already handles transaction rollback and retry at the HTTP
            # layer.  Calling rollback() inside the model method invalidates the
            # cursor and causes double-rollback errors that kill the worker.
            _logger.error(
                "update_live_location: FAILED tracker=%s error=%s",
                self.id, e, exc_info=True,
            )
            raise

    @api.model
    def _get_geofence_radius(self):
        """Get geofence radius from system parameter."""
        return float(self.env["ir.config_parameter"].sudo().get_param(
            "zencore_salesperson_tracking.geofence_radius", "100"
        ))

    @staticmethod
    def _haversine_m(lat1, lon1, lat2, lon2):
        """Distance in meters between two lat/lon points."""
        R = 6371000
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
            math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    # ── Idle Time ──────────────────────────────────────────────────────────
    # "Idle" = the salesperson stayed within IDLE_RADIUS_M of the same spot
    # for at least IDLE_MIN_MINUTES, based on the same 3m radius the mobile
    # app's own jitter filter uses to mean "hasn't moved". Segments shorter
    # than the minimum are dropped so a single red-light stop doesn't clutter
    # the tab — only genuine stationary periods (parked at a shop, stuck in
    # traffic, lunch break, etc.) show up.
    IDLE_RADIUS_M = 3.0
    IDLE_MIN_MINUTES = 3.0

    def action_recompute_idle_time(self):
        """Manual recompute button — rebuilds the Idle Time tab from scratch."""
        for tracker in self:
            tracker._compute_idle_segments()

    @api.model
    def _cron_recompute_idle_time(self):
        """Runs every few minutes (see data/idle_time_cron.xml) so the Idle
        Time tab stays roughly current on trackers that are actively live,
        without rescanning the full log on every single 2s GPS ping."""
        trackers = self.search([("is_tracking", "=", True)])
        for tracker in trackers:
            tracker._compute_idle_segments()
        return True

    def _compute_idle_segments(self):
        """Rebuild this tracker's idle_line_ids from its raw location log.

        Rebuilding (rather than incrementally appending) is what makes this
        correct even if points get backfilled or corrected later, but it
        means we have to explicitly carry forward any remarks a user already
        typed on an existing idle line — segment start_time is deterministic
        given unchanged location-log history, so we match old→new rows by
        start_time before deleting and recreating.
        """
        self.ensure_one()
        logs = self.env["salesperson.location.log"].sudo().search(
            [("tracker_id", "=", self.id)], order="tracked_at asc"
        )

        segments = []
        cur = None
        for log in logs:
            if not log.latitude and not log.longitude:
                continue
            if cur is None:
                cur = {
                    "ref_lat": log.latitude, "ref_lng": log.longitude,
                    "start": log.tracked_at, "end": log.tracked_at,
                    "location_name": log.location_name or "",
                }
                continue
            dist_m = self._haversine_m(cur["ref_lat"], cur["ref_lng"], log.latitude, log.longitude)
            if dist_m <= self.IDLE_RADIUS_M:
                cur["end"] = log.tracked_at
                if not cur["location_name"] and log.location_name:
                    cur["location_name"] = log.location_name
            else:
                segments.append(cur)
                cur = {
                    "ref_lat": log.latitude, "ref_lng": log.longitude,
                    "start": log.tracked_at, "end": log.tracked_at,
                    "location_name": log.location_name or "",
                }
        if cur is not None:
            segments.append(cur)

        old_lines = self.idle_line_ids.sudo()
        remarks_by_start = {l.start_time: l.remarks for l in old_lines if l.remarks}
        old_lines.unlink()

        vals_list = []
        for seg in segments:
            duration_min = (seg["end"] - seg["start"]).total_seconds() / 60.0
            if duration_min < self.IDLE_MIN_MINUTES:
                continue
            vals_list.append({
                "tracker_id": self.id,
                "location_name": seg["location_name"] or _("Unknown location"),
                "start_time": seg["start"],
                "end_time": seg["end"],
                "duration_minutes": duration_min,
                "remarks": remarks_by_start.get(seg["start"], False),
            })
        if vals_list:
            self.env["salesperson.tracker.idle.line"].sudo().create(vals_list)

        self.sudo().write({"last_idle_compute_at": fields.Datetime.now()})

    # ── Dashboard status (Today tab / live map) ──────────────────────────────
    # Four-way status shown as a colored dot on the manager dashboard map/list:
    #   at_customer — within AT_CUSTOMER_RADIUS_M of one of today's target
    #                 customers (dark green)
    #   moving      — actively tracking and the last two GPS points are more
    #                 than IDLE_RADIUS_M apart (light green)
    #   idle        — actively tracking but stationary, same 3m definition
    #                 used by the Idle Time tab (yellow)
    #   offline     — not tracking right now (red)
    AT_CUSTOMER_RADIUS_M = 50.0
    DASHBOARD_STATUS_COLORS = {
        "at_customer": "#065F46",  # dark green
        "moving":      "#34D399",  # light green
        "idle":        "#EAB308",  # yellow
        "offline":     "#DC2626",  # red
    }
    DASHBOARD_STATUS_LABELS = {
        "at_customer": "At Customer",
        "moving":      "Moving",
        "idle":        "Idle",
        "offline":     "Offline",
    }

    def _compute_dashboard_status(self):
        """Returns (status_key, color_hex, label) for the live dashboard."""
        self.ensure_one()
        if not self.is_tracking or not self.last_latitude or not self.last_longitude:
            status = "offline"
        else:
            status = None
            for customer in self.target_line_ids.mapped("customer_ids"):
                if not (customer.partner_latitude and customer.partner_longitude):
                    continue
                dist_m = self._haversine_m(
                    self.last_latitude, self.last_longitude,
                    customer.partner_latitude, customer.partner_longitude,
                )
                if dist_m <= self.AT_CUSTOMER_RADIUS_M:
                    status = "at_customer"
                    break
            if status is None:
                recent = self.env["salesperson.location.log"].sudo().search(
                    [("tracker_id", "=", self.id)], order="tracked_at desc", limit=2
                )
                if len(recent) >= 2:
                    dist_m = self._haversine_m(
                        recent[0].latitude, recent[0].longitude,
                        recent[1].latitude, recent[1].longitude,
                    )
                    status = "idle" if dist_m <= self.IDLE_RADIUS_M else "moving"
                else:
                    status = "moving"
        return status, self.DASHBOARD_STATUS_COLORS[status], self.DASHBOARD_STATUS_LABELS[status]

    def _check_geofence(self, latitude, longitude):
        """Auto check-in/out based on geofence_radius_meters from planned customers.
        
        Check-in: salesperson enters radius of a planned customer.
        Check-out: salesperson exits radius of the currently checked-in customer.
        Already-visited customers are skipped to avoid duplicate check-ins.
        """

        def haversine(lat1, lon1, lat2, lon2):
            R = 6371000
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * \
                math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        geofence_radius = self._get_geofence_radius()
        
        # ── STEP 1: Exit check — if currently checked in, check distance ──────
        if self.current_checkin_id and self.current_checkin_id.state == "checked_in":
            p = self.current_checkin_id.partner_id
            if p and p.partner_latitude and p.partner_longitude:
                dist_to_current = haversine(
                    latitude, longitude,
                    p.partner_latitude, p.partner_longitude
                )
                if dist_to_current > geofence_radius:
                    _logger.info(
                        "_check_geofence: EXIT tracker=%s partner=%s dist=%.1fm radius=%.1fm",
                        self.id, p.name, dist_to_current, geofence_radius
                    )
                    # Call action_checkout on the checkin record
                    self.current_checkin_id.action_checkout(latitude, longitude)
                    self.current_checkin_id = False
                else:
                    # STILL within the current customer's radius — but for
                    # closely-spaced customers (e.g. several shops on the
                    # same short street), the geofence radius (default
                    # 100m) can easily span more than one of them. Without
                    # this check, the salesperson could walk straight past
                    # 2-3 other unvisited customers while never technically
                    # exiting the FIRST one's radius, so exit/entry never
                    # fires for them and they never turn "visited" on the
                    # map — exactly the "intercepted but didn't turn dark
                    # green" symptom. If a genuinely closer, different,
                    # unvisited customer is also within geofence right now,
                    # treat it as switching visits: checkout the current one
                    # and check in to the closer one immediately.
                    self._maybe_switch_to_closer_customer(
                        latitude, longitude, geofence_radius, dist_to_current, haversine
                    )
            else:
                # Partner has no coordinates — force checkout
                self.current_checkin_id.action_checkout(latitude, longitude)
                self.current_checkin_id = False

        # ── STEP 2: Entry check — only if not currently checked in ───────────
        if self.current_checkin_id:
            return  # already inside a geofence, skip entry check

        if not self.plan_id:
            return

        # Already-visited partner IDs — skip re-entry
        visited_partner_ids = {v.partner_id.id for v in self.visited_line_ids}

        # Fetch all planned customers with coordinates in one query
        lines = self.env["salesperson.visit.plan.line"].search([
            ("plan_id", "=", self.plan_id.id),
        ])
        if not lines:
            return

        partner_ids = lines.mapped("customer_ids").filtered(
            lambda p: p.partner_latitude and p.partner_longitude
                    and p.id not in visited_partner_ids
        ).ids
        if not partner_ids:
            return

        customers = self.env["res.partner"].browse(partner_ids)

        # Find nearest unvisited customer within geofence
        nearest_customer = None
        nearest_distance = float("inf")
        for customer in customers:
            dist = haversine(
                latitude, longitude,
                customer.partner_latitude,
                customer.partner_longitude
            )
            if dist <= geofence_radius and dist < nearest_distance:
                nearest_distance = dist
                nearest_customer = customer

        if not nearest_customer:
            return  # nobody within geofence

        _logger.info(
            "_check_geofence: ENTER tracker=%s partner=%s dist=%.1fm radius=%.1fm",
            self.id, nearest_customer.name, nearest_distance, geofence_radius
        )

        target_line = self.env["salesperson.visit.plan.line"].search([
            ("plan_id", "=", self.plan_id.id),
            ("customer_ids", "in", nearest_customer.id),
        ], limit=1)

        checkin_time = fields.Datetime.now()
        
        # Create checkin record
        checkin = self.env["salesperson.checkin"].create({
            "tracker_id": self.id,
            "partner_id": nearest_customer.id,
            "target_line_id": target_line.id if target_line else False,
            "location_name": nearest_customer.display_name,
            "checkin_latitude": latitude,
            "checkin_longitude": longitude,
            "checkin_time": checkin_time,
            "state": "checked_in",
        })
        self.current_checkin_id = checkin.id

        # Note: The visited line will be created by checkin's action_checkout
        # when the user exits. No need to create it here.

        if not self.checkin_time:
            self.checkin_time = checkin_time
            
        # Force recompute of visited count
        self._compute_counts()

    def _maybe_switch_to_closer_customer(self, latitude, longitude, geofence_radius, dist_to_current, haversine):
        """Called while still checked-in to a customer but not yet outside
        their radius. If a different, unvisited customer's OWN geofence
        radius also contains the current position right now, switch to
        them immediately (checkout current, checkin new) instead of
        waiting for a full exit from the current one that might never come
        when geofences of nearby customers overlap.

        Note: this used to require the other customer to be strictly
        CLOSER than the current one before switching — but on a street
        with several customers clustered together, the currently
        checked-in customer can stay the nominally "nearest" one for the
        entire walk past several others, so that stricter check could
        still miss genuine visits. Being inside that OTHER customer's own
        radius at all is a real visit regardless of which one is nearer.
        """
        self.ensure_one()
        if not self.plan_id or not self.current_checkin_id:
            return

        current_partner_id = self.current_checkin_id.partner_id.id
        visited_partner_ids = {v.partner_id.id for v in self.visited_line_ids}
        visited_partner_ids.add(current_partner_id)

        lines = self.env["salesperson.visit.plan.line"].search([("plan_id", "=", self.plan_id.id)])
        if not lines:
            return
        candidates = lines.mapped("customer_ids").filtered(
            lambda p: p.partner_latitude and p.partner_longitude and p.id not in visited_partner_ids
        )
        if not candidates:
            return

        nearest_customer = None
        nearest_distance = float("inf")
        for customer in candidates:
            dist = haversine(latitude, longitude, customer.partner_latitude, customer.partner_longitude)
            if dist <= geofence_radius and dist < nearest_distance:
                nearest_distance = dist
                nearest_customer = customer

        if not nearest_customer:
            return

        _logger.info(
            "_check_geofence: SWITCH tracker=%s from=%s to=%s dist=%.1fm radius=%.1fm",
            self.id, self.current_checkin_id.partner_id.name, nearest_customer.name,
            nearest_distance, geofence_radius,
        )
        self.current_checkin_id.action_checkout(latitude, longitude)
        self.current_checkin_id = False

        target_line = self.env["salesperson.visit.plan.line"].search([
            ("plan_id", "=", self.plan_id.id),
            ("customer_ids", "in", nearest_customer.id),
        ], limit=1)
        checkin_time = fields.Datetime.now()
        checkin = self.env["salesperson.checkin"].create({
            "tracker_id": self.id,
            "partner_id": nearest_customer.id,
            "target_line_id": target_line.id if target_line else False,
            "location_name": nearest_customer.display_name,
            "checkin_latitude": latitude,
            "checkin_longitude": longitude,
            "checkin_time": checkin_time,
            "state": "checked_in",
        })
        self.current_checkin_id = checkin.id
        self._compute_counts()

    def _reverse_geocode(self, latitude, longitude):
        """Get location name from coordinates."""
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                headers={"User-Agent": "Odoo ZenCore Tracking"},
                params={
                    "format": "jsonv2",
                    "lat": latitude,
                    "lon": longitude,
                    "zoom": 18,
                    "accept-language": "en",
                },
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("display_name", "").split(",")[0]
        except Exception:
            pass
        return False

    def action_start_tracking(self):
        """Start a new tracking session (idempotent — safe to call when already active)."""
        self.ensure_one()
        _logger.info("action_start_tracking: tracker=%s user=%s is_tracking=%s", 
                    self.id, self.user_id.name, self.is_tracking)

        # If already tracking, do nothing — prevents duplicate sessions
        if self.is_tracking and self.current_session_id and self.current_session_id.state == "active":
            _logger.info(
                "action_start_tracking: tracker=%s already active (session=%s) — no-op",
                self.id, self.current_session_id.id,
            )
            return

        # Close any orphaned open session before creating a new one
        old_session = self.current_session_id
        if old_session and old_session.state == "active":
            _logger.warning(
                "action_start_tracking: closing orphaned session=%s for tracker=%s",
                old_session.id, self.id,
            )
            try:
                old_session.action_stop()
            except Exception as e:
                _logger.warning("action_start_tracking: error closing orphaned session: %s", e)

        # Create new session
        try:
            session = self.env["salesperson.tracking.session"].create({
                "tracker_id": self.id,
                "start_time": fields.Datetime.now(),
                "state": "active",
            })
            _logger.info("action_start_tracking: created session=%s for tracker=%s", session.id, self.id)
        except Exception as e:
            _logger.error("action_start_tracking: failed to create session: %s", e, exc_info=True)
            raise

        vals = {
            "is_tracking": True,
            "current_session_id": session.id,
            "state": "live",
        }
        if not self.checkin_time:
            vals["checkin_time"] = fields.Datetime.now()
        
        try:
            self.write(vals)
            _logger.info("action_start_tracking: wrote values %s", vals)
        except Exception as e:
            _logger.error("action_start_tracking: failed to write tracker values: %s", e, exc_info=True)
            raise
        
        # Flush to ensure changes are committed
        self.env.cr.commit()

        # Wake the salesman's installed mobile app, regardless of which
        # device (PC/laptop/mobile browser) called this method. No-ops
        # silently if the app isn't installed / no push token registered —
        # the browser's own GPS loop keeps working as the fallback for
        # anyone without the app.
        try:
            self.user_id.sudo()._send_push_trigger('start', self.id)
        except Exception as e:
            _logger.warning("action_start_tracking: push trigger failed: %s", e)

        _logger.info("action_start_tracking: completed successfully for tracker=%s", self.id)

    def action_stop_tracking(self):
        """Stop the current tracking session."""
        self.ensure_one()
        _logger.info("action_stop_tracking: tracker=%s user=%s", self.id, self.user_id.name)

        try:
            if self.current_session_id:
                self.current_session_id.action_stop()

            # If still checked in, checkout before stopping
            if self.current_checkin_id and self.current_checkin_id.state == "checked_in":
                try:
                    self.current_checkin_id.action_checkout()
                except Exception as e:
                    _logger.warning("action_stop_tracking: error during checkout: %s", e)

            self.write({
                "is_tracking": False,
                "current_session_id": False,
                "checkout_time": fields.Datetime.now(),
                # Offline, not back to Planned — Planned only applies before the
                # very first Start. From here, pressing Start again goes
                # straight Offline -> Live (see action_start_tracking above).
                "state": "offline",
            })

            try:
                self.user_id.sudo()._send_push_trigger('stop', self.id)
            except Exception as e:
                _logger.warning("action_stop_tracking: push trigger failed: %s", e)

            try:
                self._compute_idle_segments()
            except Exception as e:
                _logger.warning("action_stop_tracking: idle-time recompute failed: %s", e)

            _logger.info("action_stop_tracking: tracker=%s stopped successfully", self.id)
        except Exception as e:
            _logger.error("action_stop_tracking: error: %s", e, exc_info=True)
            raise

    def action_load_target_lines(self):
        """Load target lines from visit plan."""
        self.ensure_one()
        if not self.plan_id:
            return

        # Clear existing target lines
        self.target_line_ids.unlink()

        for plan_line in self.plan_id.target_line_ids:
            self.env["salesperson.tracker.target.line"].create({
                "tracker_id": self.id,
                "plan_line_id": plan_line.id,
                "expected_time_minutes": plan_line.expected_time_minutes,
                "employee_ids": [(6, 0, plan_line.employee_ids.ids)],
                "from_location": plan_line.from_location,
                "to_location": plan_line.to_location,
                "expected_km": plan_line.expected_km,
                "customer_ids": [(6, 0, plan_line.customer_ids.ids)],
                "notes": plan_line.notes,
            })

    def action_open_live_tracking_page(self):
        """Smart routing, per clicked record:
        - MY OWN tracker for TODAY  → personal /live page (has Start/Stop controls).
        - Anything else (someone else's tracker, or my own from a past day) →
          read-only /moving_map/<id> for that specific record.
        This prevents /live silently creating a brand-new blank tracker for
        whoever clicks "Live Page" on a record that isn't their own today's one
        (e.g. a manager opening a salesman's card).

        Returned as an ir.actions.client (iframe embed) rather than
        ir.actions.act_url — this keeps the Odoo app shell (top menu bar,
        breadcrumb) visible around the page instead of navigating away from
        it entirely, matching how the Dashboard is embedded. See
        static/src/js/salesperson_iframe_action.js.
        """
        self.ensure_one()
        today = fields.Date.today()
        if self.user_id.id == self.env.user.id and self.visit_date == today:
            return {
                "type": "ir.actions.client",
                "tag": "salesperson_iframe_action",
                "name": "Live Tracking",
                "params": {
                    # The "?_=<timestamp>" cache-buster + the server's own
                    # Cache-Control: no-store (see controllers/main.py:
                    # _no_cache()) together guarantee this always loads a
                    # fresh page for whoever is CURRENTLY logged in, never a
                    # stale cached copy from an earlier session/user.
                    "url": "/salesperson_tracking/live?_=%d" % int(time.time()),
                    "title": "Live Tracking",
                },
            }
        return self.action_view_moving_map()

    def action_view_moving_map(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "salesperson_iframe_action",
            "name": "Movement Map",
            "params": {
                "url": f"/salesperson_tracking/moving_map/{self.id}?_={int(time.time())}",
                "title": "Movement Map",
            },
        }

    def action_view_location_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Location History",
            "res_model": "salesperson.location.log",
            "view_mode": "list,form",
            "domain": [("tracker_id", "=", self.id)],
            "context": {"default_tracker_id": self.id},
        }

    def action_print_tracking_report(self):
        return self.env.ref("zencore_salesperson_tracking.action_report_tracking_summary").report_action(self)

    @api.model
    def _cleanup_stale_sessions(self):
        """Clean up sessions that have been idle for too long."""
        thirty_min_ago = fields.Datetime.now() - timedelta(minutes=30)
        
        stale_trackers = self.search([
            ('is_tracking', '=', True),
            ('last_seen', '<', thirty_min_ago),
        ])
        
        for tracker in stale_trackers:
            try:
                tracker.action_stop_tracking()
                _logger.info("Auto-stopped tracking for %s (tracker %s) due to inactivity", tracker.user_id.name, tracker.id)
            except Exception as e:
                _logger.error("Failed to auto-stop tracker %s: %s", tracker.id, e, exc_info=True)
        
        return True

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        """Self-heal past-day trackers before every search.

        The nightly cron (action_auto_complete_past_trackers, ~00:05) is
        the primary mechanism for flipping yesterday's trackers to
        'completed', but relying on a cron alone means the UI can show a
        stale Offline/Live pill for a day that's already over if the cron
        hasn't run yet (or is disabled/paused, common on staging DBs) —
        this closes that gap by re-running the same cheap check right
        before every list/kanban/search of this model, so it's always
        correct regardless of cron timing. Guarded by a context flag to
        avoid infinite recursion (the auto-complete call below also
        searches this model).
        """
        if not self.env.context.get('_tracker_autocomplete_running'):
            try:
                self.with_context(_tracker_autocomplete_running=True).sudo().action_auto_complete_past_trackers()
            except Exception as e:
                _logger.warning("search: self-heal auto-complete failed (non-fatal): %s", e)
        return super().search(domain, offset=offset, limit=limit, order=order)

    @api.model
    def action_auto_complete_past_trackers(self):
        """Scheduled action: auto-mark past-day trackers as 'completed'.
        Runs daily at midnight+5min. Stops any still-active tracking session
        before transitioning state so GPS logs are closed cleanly.
        """
        today = fields.Date.today()
        past_trackers = self.search([
            ('visit_date', '<', today),
            ('state', 'in', ['planned', 'offline', 'live']),
        ])
        for tracker in past_trackers:
            try:
                if tracker.is_tracking:
                    try:
                        tracker.action_stop_tracking()
                    except Exception as e:
                        # action_stop_tracking() re-raises internally on any
                        # failure (session/checkin cleanup, etc.) — without
                        # this inner try/except, that exception would abort
                        # this loop iteration BEFORE the completed-write
                        # below ever runs, permanently stranding a past
                        # record in planned/offline/live state. The
                        # completed transition must never depend on
                        # subsidiary cleanup succeeding.
                        _logger.warning(
                            "action_auto_complete_past_trackers: action_stop_tracking failed for "
                            "tracker=%s, forcing completed state anyway: %s", tracker.id, e,
                        )
                # Always force completed + not-tracking, regardless of
                # whether the stop-tracking cleanup above succeeded.
                tracker.write({'state': 'completed', 'is_tracking': False})
                _logger.info(
                    "action_auto_complete_past_trackers: completed tracker=%s user=%s date=%s",
                    tracker.id, tracker.user_id.name, tracker.visit_date,
                )
            except Exception as e:
                _logger.error(
                    "action_auto_complete_past_trackers: failed for tracker=%s: %s",
                    tracker.id, e, exc_info=True,
                )
        return True

    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        """Auto-load target lines whenever a visit plan is linked."""
        if self.plan_id:
            self.action_load_target_lines()

class SalespersonTrackerTargetLine(models.Model):
    _name = "salesperson.tracker.target.line"
    _description = "Tracker Target Line"

    tracker_id = fields.Many2one("salesperson.tracker", required=True, ondelete="cascade")
    plan_line_id = fields.Many2one("salesperson.visit.plan.line", string="Plan Line")

    expected_time_minutes = fields.Integer(string="Expected Time (min)")
    employee_ids = fields.Many2many("hr.employee", string="Accompanies")
    from_location = fields.Char(string="From Location")
    to_location = fields.Char(string="To Location")
    expected_km = fields.Float(string="Expected KM", digits=(16, 2))
    customer_ids = fields.Many2many("res.partner", string="Customers")
    notes = fields.Text(string="Notes")

    customers_visited_html = fields.Html(
        string="Customers", compute="_compute_customers_visited_html", sanitize=False,
        help="Same customers as the Customers field, rendered as chips — dark "
             "green once that customer has actually been checked in+out "
             "(appears in Visited Lines), grey while still pending.",
    )

    @api.depends("customer_ids", "tracker_id.visited_line_ids.partner_id")
    def _compute_customers_visited_html(self):
        for line in self:
            visited_partner_ids = set(line.tracker_id.visited_line_ids.mapped("partner_id").ids)
            chips = []
            for customer in line.customer_ids:
                if customer.id in visited_partner_ids:
                    style = "background:#065F46;color:#fff;"
                else:
                    style = "background:#E2E8F0;color:#334155;"
                chips.append(
                    '<span style="display:inline-block;padding:2px 8px;margin:2px 3px 2px 0;'
                    'border-radius:10px;font-size:12px;line-height:18px;%s">%s</span>'
                    % (style, customer.name or '')
                )
            line.customers_visited_html = ''.join(chips) or ''


class SalespersonTrackerVisitedLine(models.Model):
    _name = "salesperson.tracker.visited.line"
    _description = "Tracker Visited Line"

    tracker_id = fields.Many2one("salesperson.tracker", required=True, ondelete="cascade")
    checkin_id = fields.Many2one("salesperson.checkin", string="Check-In Record")
    partner_id = fields.Many2one("res.partner", string="Customer", required=True)

    checkin_time = fields.Datetime(string="In", help="Auto-recorded when entering 100m radius")
    checkout_time = fields.Datetime(string="Exit", help="Auto-recorded when exiting 100m radius")
    time_spent_minutes = fields.Float(string="Time Spent (min)", compute="_compute_time_spent", store=True)

    rating = fields.Selection([
        ("1", "★ Poor"),
        ("2", "★★ Fair"),
        ("3", "★★★ Good"),
        ("4", "★★★★ Very Good"),
        ("5", "★★★★★ Excellent"),
    ], string="Rating")

    @api.depends("checkin_time", "checkout_time")
    def _compute_time_spent(self):
        for line in self:
            if line.checkin_time and line.checkout_time:
                delta = line.checkout_time - line.checkin_time
                line.time_spent_minutes = delta.total_seconds() / 60.0
            else:
                line.time_spent_minutes = 0.0


class SalespersonTrackerIdleLine(models.Model):
    _name = "salesperson.tracker.idle.line"
    _description = "Tracker Idle Time"
    _order = "start_time desc"

    tracker_id = fields.Many2one("salesperson.tracker", required=True, ondelete="cascade")

    location_name = fields.Char(string="Location Name", help="Auto-filled from the location log's reverse-geocoded name.")
    start_time = fields.Datetime(string="Idle Since")
    end_time = fields.Datetime(string="Idle Until")
    duration_minutes = fields.Float(string="Total Time Spent (min)", help="Auto-computed: how long the salesperson stayed within ~3m of this spot.")
    remarks = fields.Text(string="Remarks", help="Manual note — e.g. why the salesperson was stationary here (break, traffic, customer visit, etc.).")