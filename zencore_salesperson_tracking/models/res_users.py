from odoo import fields, models, api
import logging
import time
import requests

_logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class ResUsers(models.Model):
    _inherit = "res.users"

    salesperson_role = fields.Selection(
        [
            ("manager", "Manager"),
            ("salesman", "Salesman"),
        ],
        string="Role",
        default="salesman",
        required=True,
        help="Manager: Full access to all tracking data\nSalesman: Own records only",
    )

    salesperson_tracker_ids = fields.One2many(
        "salesperson.tracker",
        "user_id",
        string="Tracking Reports",
    )

    expo_push_token = fields.Char(
        string="Mobile Push Token",
        help="Set automatically by the ZenCore Tracker app after login. Used to "
             "silently wake the app's background GPS service when Start/Stop "
             "Tracking is pressed from ANY device (PC, laptop, or mobile browser) "
             "— not just from the phone itself.",
    )

    # ── Keep salesperson_role in sync with the REAL security groups ──────────
    # `salesperson_role` (the Manager/Salesman dropdown on the user form) is
    # what this module's own custom pages check (Dashboard, /live,
    # /moving_map). But the Odoo BACKEND views — Live Tracking kanban/list —
    # are gated by ir.rule records tied to the ACTUAL security groups
    # (group_salesperson_manager / group_salesperson_salesman). Those two
    # were never linked: setting the Role dropdown to "Manager" never
    # actually added the user to group_salesperson_manager, so the "see
    # everyone's records" ir.rule never applied to them — the backend
    # kanban/list silently stayed restricted to their own records only.
    # This keeps both in sync going forward.
    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users:
            user._sync_salesperson_role_groups()
        return users

    def write(self, vals):
        res = super().write(vals)
        # Only re-sync when 'salesperson_role' was part of THIS write — the
        # sync itself writes only 'group_ids' (never 'salesperson_role'),
        # so this guard also naturally prevents infinite recursion without
        # needing a separate context flag.
        if 'salesperson_role' in vals:
            for user in self:
                user._sync_salesperson_role_groups()
        return res

    def _sync_salesperson_role_groups(self):
        self.ensure_one()
        manager_group = self.env.ref('zencore_salesperson_tracking.group_salesperson_manager', raise_if_not_found=False)
        salesman_group = self.env.ref('zencore_salesperson_tracking.group_salesperson_salesman', raise_if_not_found=False)
        if not manager_group or not salesman_group:
            return  # groups not loaded yet (e.g. mid-install) — nothing to sync
        if self.salesperson_role == 'manager':
            commands = [(4, manager_group.id), (3, salesman_group.id)]
        else:
            commands = [(3, manager_group.id), (4, salesman_group.id)]
        self.sudo().write({'group_ids': commands})

    def _register_hook(self):
        """Runs automatically on every server start / module load — no new
        XML data file needed. This retroactively fixes any user whose
        salesperson_role was already set to "Manager" before the sync
        above existed (e.g. every database that installed an earlier
        version of this module), so a plain module upgrade is enough —
        nobody has to re-pick their Role from the dropdown to fix it.
        Idempotent and cheap: only writes users that are actually out of
        sync.
        """
        super()._register_hook()
        try:
            manager_group = self.env.ref('zencore_salesperson_tracking.group_salesperson_manager', raise_if_not_found=False)
            salesman_group = self.env.ref('zencore_salesperson_tracking.group_salesperson_salesman', raise_if_not_found=False)
            if not manager_group or not salesman_group:
                return
            managers_out_of_sync = self.sudo().search([
                ('salesperson_role', '=', 'manager'),
                ('group_ids', 'not in', manager_group.id),
            ])
            salesmen_out_of_sync = self.sudo().search([
                ('salesperson_role', '=', 'salesman'),
                ('group_ids', 'not in', salesman_group.id),
            ])
            for user in managers_out_of_sync | salesmen_out_of_sync:
                user._sync_salesperson_role_groups()
        except Exception as e:
            _logger.warning("_register_hook: salesperson role/group self-heal failed (non-fatal): %s", e)

    def _send_push_trigger(self, action, tracker_id):
        """Silently wake the ZenCore Tracker app on this user's phone.

        No-ops (does nothing, raises nothing) if the user has no app
        installed / no push token registered — the browser's own GPS loop
        remains the fallback for those users, exactly as before.
        """
        self.ensure_one()
        if not self.expo_push_token:
            return
        try:
            response = requests.post(
                EXPO_PUSH_URL,
                json={
                    "to": self.expo_push_token,
                    "data": {"action": action, "tracker_id": tracker_id},
                    "priority": "high",
                    # No title/body/sound → delivered as a silent data
                    # message; Android wakes the app's background task
                    # handler without showing a notification tray entry.
                    "_contentAvailable": True,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=5,
            )
            _logger.info(
                "_send_push_trigger: user=%s action=%s tracker=%s status=%s",
                self.name, action, tracker_id, response.status_code,
            )
        except Exception as e:
            _logger.warning(
                "_send_push_trigger: failed to notify user=%s action=%s: %s",
                self.name, action, e,
            )

    def action_open_live_tracking_page(self):
        """Open live tracking page.

        Does NOT unconditionally create a tracker — only ensures one when an
        existing tracker or an approved plan for today already justifies it.
        This mirrors the guard in controllers/main.py:live_tracking_page()
        so this method (currently unreferenced by any view, kept for API
        parity) can never reintroduce the ghost-tracker bug if wired up later.
        """
        self.ensure_one()
        today = fields.Date.today()
        existing_tracker = self.env['salesperson.tracker'].search([
            ('user_id', '=', self.id), ('visit_date', '=', today),
        ], limit=1)
        if not existing_tracker:
            has_approved_plan = self.env['salesperson.visit.plan'].search_count([
                ('user_id', '=', self.id), ('visit_date', '=', today), ('state', '=', 'approved'),
            ])
            if has_approved_plan:
                self._ensure_salesperson_tracker()
        return {
            "type": "ir.actions.client",
            "tag": "salesperson_iframe_action",
            "name": "Live Tracking",
            "params": {
                "url": "/salesperson_tracking/live?_=%d" % int(time.time()),
                "title": "Live Tracking",
            },
        }

    def _ensure_salesperson_tracker(self):
        """Ensure a tracker exists for today for this user.

        Returns an existing tracker for today or creates a new one.
        Also attempts to link a matching visit plan if one exists.
        """
        self.ensure_one()
        today = fields.Date.today()

        # order='id desc' → always return the most recently created tracker for today.
        # Without this, Postgres returns an arbitrary one (usually oldest), causing
        # GPS updates and geofence checks to go to the wrong tracker when 2 exist.
        tracker = self.env['salesperson.tracker'].search([
            ('user_id', '=', self.id),
            ('visit_date', '=', today),
        ], order='id desc', limit=1)

        if tracker:
            _logger.debug(
                "_ensure_salesperson_tracker: found existing tracker id=%s for user=%s date=%s",
                tracker.id, self.name, today,
            )
            return tracker

        # Create a new tracker for today
        tracker = self.env['salesperson.tracker'].create({
            'user_id': self.id,
            'visit_date': today,
            'state': 'planned',
        })
        _logger.info(
            "_ensure_salesperson_tracker: created new tracker id=%s for user=%s date=%s",
            tracker.id, self.name, today,
        )

        # Link a plan for today if one exists
        plan = self.env['salesperson.visit.plan'].search([
            ('user_id', '=', self.id),
            ('visit_date', '=', today),
        ], limit=1)
        if plan:
            tracker.plan_id = plan.id
            tracker.action_load_target_lines()
            _logger.info(
                "_ensure_salesperson_tracker: linked plan id=%s to tracker id=%s for user=%s",
                plan.id, tracker.id, self.name,
            )
        else:
            _logger.debug(
                "_ensure_salesperson_tracker: no plan found for user=%s date=%s",
                self.name, today,
            )

        return tracker
